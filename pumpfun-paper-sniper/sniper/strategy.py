"""
strategy.py -- die Handelsregeln: wann kaufen, wann verkaufen.

Der Ablauf in Worten
--------------------
1. Ein neuer Token taucht im Feed auf -> er wird ein "Kandidat".
2. Fuer `signal_window_sec` Sekunden schaut der Bot nur zu und misst:
     - wie viel SOL netto in die Bonding Curve fliesst (Kaufdruck)
     - wie stark der Preis in diesem Fenster steigt (Momentum)
     - wie weit die Kurve schon gelaufen ist (Curve Progress)
3. Am Ende des Fensters entscheidet `evaluate_entry()`: kaufen oder verwerfen.
   Es muessen ALLE Filter passen - ein einziger Fehlschlag reicht zum Skip.
4. Ist die Position offen, prueft `decide_exit()` bei jedem Kurs-Tick die
   Ausstiegsregeln - in einer festen Prioritaetsreihenfolge:

       Migriert -> Rug -> Stop-Loss -> (Teil-)Take-Profit -> Trailing
                -> Net-Sell-Flip -> Hard-Time-Stop

   Die Reihenfolge ist wichtig: ein Rug soll auch dann rausbringen, wenn der
   Kurs formal noch ueber dem Einstieg liegt.

Dieses Modul rechnet nur und entscheidet - es bucht nichts. Das Buchen macht
die paper_engine. Dadurch laesst sich die Strategie separat testen
(siehe tests/test_strategy.py).
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

from .config import Config
from .curve import CurveState
from .feed import NewTokenEvent
from .paper_engine import ExitReason, Position

#: 1 SOL in Lamports - fuer die Umrechnung der Reserve-Deltas.
LAMPORTS_PER_SOL = 1_000_000_000


# ---------------------------------------------------------------------------
# Fluss-Messung: wie viel SOL geht netto rein oder raus?
# ---------------------------------------------------------------------------
class FlowTracker:
    """
    Merkt sich den Verlauf der SOL-Reserve einer Bonding Curve.

    Gemessen wird `real_sol_reserves` - also das SOL, das TATSAECHLICH in der
    Kurve liegt. Jeder Kauf erhoeht es, jeder Verkauf senkt es. Die
    Veraenderung IST damit per Definition der Nettofluss, und man braucht
    keinen (kostenpflichtigen) Trade-Stream.

    Frueher wurde stattdessen `virtual_sol_reserves` benutzt. Das ist zwar die
    Groesse, aus der sich der Preis ergibt, aber als Flussmass gefaehrlich:
    Weicht ein Account vom Standardlayout ab, liefert es Fantasiewerte - im
    Betrieb wurden so "24.85 SOL Kaufdruck" bei einer Kurve gemeldet, in die
    physikalisch nur 0.5 SOL passen. Das reale Feld ist durch die Realitaet
    begrenzt und kann das nicht.
    """

    def __init__(self, max_samples: int = 240) -> None:
        # (Zeitpunkt, reale SOL-Reserve in Lamports)
        self._samples: deque[tuple[float, int]] = deque(maxlen=max_samples)

    def add(self, timestamp: float, real_sol_reserves: int) -> None:
        self._samples.append((timestamp, real_sol_reserves))

    @property
    def sample_count(self) -> int:
        return len(self._samples)

    def net_flow_sol(self, window_sec: float, now: float | None = None) -> float:
        """
        Netto-SOL-Fluss der letzten `window_sec` Sekunden.
        Positiv = es wurde netto gekauft, negativ = netto verkauft.

        Gibt 0.0 zurueck, solange noch nicht genug Messpunkte da sind.
        """
        if len(self._samples) < 2:
            return 0.0

        now = now if now is not None else time.monotonic()
        cutoff = now - window_sec

        # Aeltester Messpunkt, der noch im Fenster liegt. Liegt keiner im
        # Fenster, nehmen wir den aeltesten ueberhaupt - dann ist der Wert
        # konservativ (aelter = groesseres Fenster).
        baseline = self._samples[0][1]
        for timestamp, reserves in self._samples:
            if timestamp >= cutoff:
                baseline = reserves
                break

        latest = self._samples[-1][1]
        return (latest - baseline) / LAMPORTS_PER_SOL

    def total_flow_sol(self, baseline_lamports: int) -> float:
        """Netto-Fluss gegenueber einem festen Startwert (Beginn des Fensters)."""
        if not self._samples:
            return 0.0
        return (self._samples[-1][1] - baseline_lamports) / LAMPORTS_PER_SOL


# ---------------------------------------------------------------------------
# Kandidat: ein Token im Beobachtungsfenster
# ---------------------------------------------------------------------------
@dataclass
class Candidate:
    """
    Ein neuer Token, der gerade beobachtet (aber noch nicht gekauft) wird.

    WICHTIG zu den Startwerten
    --------------------------
    `start_price` und `start_sol_reserves` werden beim ERSTEN Kursabruf von der
    Blockchain gesetzt - nicht aus dem Feed-Event.

    Das war urspruenglich anders und hat zu falschen Messwerten gefuehrt: Der
    Startwert kam aus dem Event (`vSolInBondingCurve`), alle weiteren Werte von
    der Kette. Zwei verschiedene Quellen voneinander abzuziehen ergibt keinen
    sinnvollen Fluss - im Betrieb meldete der Bot dadurch z.B. "13,10 SOL
    Kaufdruck" bei einem Token, dessen Kurve laut Progress nur ~1,3 SOL
    enthalten konnte.

    Regel daraus: Deltas immer aus derselben Quelle bilden. Der Preis am
    Fensteranfang kostet so zwar bis zu einen Poll-Zyklus Verzoegerung, ist
    dafuer aber mit allen spaeteren Messwerten vergleichbar.
    """

    event: NewTokenEvent
    #: Preis beim ersten Kursabruf. 0.0, solange noch keiner vorliegt.
    start_price: float = 0.0
    #: Reale SOL-Reserve beim ersten Kursabruf (Lamports).
    #: None = noch keine Messung.
    start_sol_reserves: int | None = None
    flow: FlowTracker = field(default_factory=FlowTracker)

    last_state: CurveState | None = None
    last_price: float = 0.0
    max_price: float = 0.0
    ticks: int = 0

    @property
    def mint(self) -> str:
        return self.event.mint

    @property
    def bonding_curve(self) -> str:
        return self.event.bonding_curve

    @property
    def age_sec(self) -> float:
        """Alter des Tokens, gerechnet ab dem Empfang des Launch-Events."""
        return time.monotonic() - self.event.received_at

    def on_tick(self, state: CurveState, now: float) -> None:
        """
        Neuen Kurs-Messpunkt aufnehmen. Der erste Messpunkt legt gleichzeitig
        die Vergleichsbasis fuer Kaufdruck und Momentum fest.
        """
        self.last_state = state
        self.ticks += 1

        price = state.price_sol
        if price > 0:
            self.last_price = price
            self.max_price = max(self.max_price, price)
            if self.start_price <= 0:
                self.start_price = price

        if self.start_sol_reserves is None:
            self.start_sol_reserves = state.real_sol_reserves

        self.flow.add(now, state.real_sol_reserves)

    @property
    def price_gain_pct(self) -> float:
        """Kursgewinn seit Beginn des Beobachtungsfensters, in Prozent."""
        if self.start_price <= 0 or self.last_price <= 0:
            return 0.0
        return (self.last_price / self.start_price - 1.0) * 100.0

    @property
    def net_buy_volume_sol(self) -> float:
        """
        Netto in die Kurve geflossenes SOL seit dem ersten Messpunkt.
        0.0, solange noch keine Vergleichsbasis vorliegt.
        """
        if self.start_sol_reserves is None:
            return 0.0
        return self.flow.total_flow_sol(self.start_sol_reserves)


def make_candidate(event: NewTokenEvent) -> Candidate:
    """
    Baut aus einem Feed-Event einen Kandidaten.

    Die Vergleichswerte fuer Kaufdruck und Momentum werden bewusst NICHT aus
    dem Event uebernommen, sondern beim ersten Kursabruf von der Kette gesetzt
    (siehe Docstring von `Candidate`).
    """
    return Candidate(event=event)


# ---------------------------------------------------------------------------
# Einstiegsentscheidung
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class EntryDecision:
    """Ergebnis der Einstiegspruefung."""

    buy: bool
    reason: str  # bei buy=False: welcher Filter gerissen hat


def evaluate_entry(candidate: Candidate, cfg: Config) -> EntryDecision:
    """
    Prueft alle Einstiegsfilter aus der config.yaml.
    ALLE muessen passen, sonst wird der Token verworfen.
    """
    state = candidate.last_state

    # 0) Ueberhaupt Kursdaten da? Ohne RPC-Antwort kein Kauf.
    if state is None:
        return EntryDecision(False, "keine Kursdaten (RPC)")
    if candidate.last_price <= 0:
        return EntryDecision(False, "kein gueltiger Preis")

    # 0b) Mindestens zwei Messpunkte, sonst gibt es keine Veraenderung zu
    #     messen - Kaufdruck und Momentum waeren beide zwangslaeufig 0.
    if candidate.ticks < 2 or candidate.start_sol_reserves is None:
        return EntryDecision(False, f"zu wenig Messpunkte ({candidate.ticks})")

    # 1) Migriert / abgeschlossen?
    if cfg.skip_if_complete and not state.is_tradable:
        return EntryDecision(False, "Token migriert (complete)")

    # 1b) Verhaelt sich der Account ueberhaupt wie eine pump.fun-Kurve?
    #     Wenn nicht, sind Preis, Progress und Kaufdruck allesamt Fantasie -
    #     dann wird nicht gehandelt. (Siehe CurveState.is_standard_layout.)
    if not state.is_standard_layout(cfg.advanced.max_curve_layout_deviation_sol):
        return EntryDecision(
            False, f"kein Standard-Kurvenlayout "
                   f"(Abweichung {state.layout_deviation_sol:+.2f} SOL)")

    # 2) Alter: nur ganz frische Token
    age = candidate.age_sec
    if age > cfg.max_token_age_sec:
        return EntryDecision(False, f"zu alt ({age:.0f}s > {cfg.max_token_age_sec:.0f}s)")

    # 3) Curve Progress: nicht zu frueh (tot), nicht zu spaet (schon gelaufen)
    progress = state.progress_pct(cfg.advanced.initial_real_token_reserves)
    if progress < cfg.min_curve_progress_pct:
        return EntryDecision(
            False, f"Progress zu niedrig ({progress:.1f}% < {cfg.min_curve_progress_pct}%)")
    if progress > cfg.max_curve_progress_pct:
        return EntryDecision(
            False, f"Progress zu hoch ({progress:.1f}% > {cfg.max_curve_progress_pct}%)")

    # 4) Kaufdruck im Fenster
    net_buy = candidate.net_buy_volume_sol
    if net_buy < cfg.min_net_buy_volume_sol:
        return EntryDecision(
            False, f"Kaufdruck zu klein ({net_buy:.2f} < {cfg.min_net_buy_volume_sol} SOL)")

    # 5) Momentum: Preis muss im Fenster angezogen haben
    gain = candidate.price_gain_pct
    if gain < cfg.min_price_gain_in_window_pct:
        return EntryDecision(
            False, f"Momentum zu schwach ({gain:+.1f}% < "
                   f"{cfg.min_price_gain_in_window_pct}%)")

    # 5b) Laeuft der Abverkauf JETZT GERADE schon?
    #
    #     Der Kaufdruck oben wird ueber das ganze Fenster gemessen (z.B. 10 s).
    #     Der bleibt positiv, auch wenn in den letzten zwei Sekunden bereits
    #     abverkauft wird. Genau so hat der Bot Spitzen gekauft, die schon am
    #     Kippen waren - und die Position eine Sekunde spaeter per Net-Sell-Flip
    #     mit Verlust wieder geschlossen. Zweimal Gebuehren fuer nichts.
    #
    #     Grundregel: Keine Position eroeffnen, die die Ausstiegslogik im
    #     naechsten Tick sofort wieder schliessen wuerde. Deshalb wird hier
    #     bewusst mit demselben Fenster und derselben Schwelle geprueft wie
    #     beim Flip-Ausstieg.
    if cfg.exit_on_net_sell_flip:
        window = cfg.advanced.net_sell_flip_window_sec
        recent_flow = candidate.flow.net_flow_sol(window)
        if recent_flow <= -abs(cfg.advanced.net_sell_flip_threshold_sol):
            return EntryDecision(
                False, f"Abverkauf laeuft bereits ({recent_flow:+.2f} SOL "
                       f"in {window:.0f}s)")

    # 5c) Ist der Token schon zu weit gelaufen?
    #     Wer bei +200 % im Zehn-Sekunden-Fenster einsteigt, kauft die Spitze.
    #     Standardmaessig aus (0 = keine Obergrenze), siehe config.yaml.
    cap = cfg.advanced.max_price_gain_in_window_pct
    if cap > 0 and gain > cap:
        return EntryDecision(
            False, f"schon zu weit gelaufen ({gain:+.1f}% > {cap:.0f}%)")

    # 6) Dev-Anteil: haelt der Ersteller zu viel, kann er den Kurs alleine kippen
    dev_pct = candidate.event.dev_holding_pct
    if dev_pct > cfg.max_dev_holding_pct:
        return EntryDecision(
            False, f"Dev haelt zu viel ({dev_pct:.1f}% > {cfg.max_dev_holding_pct}%)")

    return EntryDecision(
        True,
        f"Progress {progress:.1f}% | Kaufdruck {net_buy:.2f} SOL | Momentum {gain:+.1f}%",
    )


# ---------------------------------------------------------------------------
# Nachkauf-Entscheidung ("Pyramiding")
# ---------------------------------------------------------------------------
def should_add_to_position(
    position: Position, state: CurveState | None, cfg: Config,
    *, net_flow_sol: float,
) -> tuple[bool, str]:
    """
    Darf in eine laufende Position nachgekauft werden?

    Grundsatz: nur bei STAERKE nachlegen, nie bei Schwaeche. Eine verlierende
    Position zu verbilligen ist die klassische Art, aus einem kleinen Verlust
    einen grossen zu machen - das macht dieser Bot ausdruecklich nicht.

    Alle Bedingungen muessen erfuellt sein:
      1. Nachkaufen ist ueberhaupt erlaubt und das Limit nicht erreicht
      2. Die Position steht deutlich im Plus
      3. Der Kaufdruck ist noch da (kein laufender Abverkauf)
      4. Die Kurve ist handelbar und stimmig
    """
    if cfg.advanced.max_entries_per_token <= 1:
        return False, ""
    if position.entries >= cfg.advanced.max_entries_per_token:
        return False, ""
    if position.pending:
        return False, ""
    if state is None or not state.is_tradable:
        return False, ""
    if not state.is_standard_layout(cfg.advanced.max_curve_layout_deviation_sol):
        return False, ""

    change_pct = position.price_change_pct
    if change_pct < cfg.advanced.pyramid_min_gain_pct:
        return False, ""

    # Kippt der Kaufdruck gerade, wird nicht nachgelegt - dann steht eher der
    # Ausstieg an als ein weiterer Einstieg.
    if net_flow_sol <= -abs(cfg.advanced.net_sell_flip_threshold_sol):
        return False, ""

    return True, (f"{change_pct:+.1f}% im Plus, Zufluss {net_flow_sol:+.2f} SOL "
                  f"({position.entries + 1}. Einstieg)")


# ---------------------------------------------------------------------------
# Ausstiegsentscheidung
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ExitDecision:
    """
    Was mit einer offenen Position passieren soll.

    * `action == "hold"`    -> nichts tun
    * `action == "partial"` -> Teilverkauf in Hoehe von `fraction`
    * `action == "close"`   -> komplett schliessen
    """

    action: str           # "hold" | "partial" | "close"
    reason: str = ""      # einer der ExitReason-Werte
    fraction: float = 0.0 # nur bei "partial"
    detail: str = ""      # Klartext fuers Log


HOLD = ExitDecision("hold")


def decide_exit(
    position: Position,
    state: CurveState | None,
    cfg: Config,
    *,
    tick_drop_pct: float,
    net_flow_sol: float,
) -> ExitDecision:
    """
    Entscheidet, ob (und wie) eine Position geschlossen wird.

    Parameter:
      `tick_drop_pct`  Kursverlust seit dem letzten Tick, in Prozent
                       (positiver Wert = der Kurs ist gefallen)
      `net_flow_sol`   Netto-SOL-Fluss im Flip-Fenster
                       (negativ = es wird netto verkauft)

    Die Reihenfolge der Pruefungen ist die Prioritaet der Regeln.
    """
    # --- 0) Token migriert oder Kurve tot -> sofort raus -------------------
    # Nach der Migration laeuft der Handel auf PumpSwap weiter; die Bonding
    # Curve liefert keinen Kurs mehr. Halten waere sinnlos.
    if state is None or not state.is_tradable:
        # state=None heisst nur "RPC hat gerade nicht geantwortet" - deshalb
        # wird dann NICHT geschlossen, ausser der Zeitstopp greift (s.u.).
        if state is not None:
            return ExitDecision("close", ExitReason.MIGRATED, detail="Token migriert")
        if position.age_sec >= cfg.hard_time_stop_sec:
            return ExitDecision(
                "close", ExitReason.TIME_STOP,
                detail=f"Zeitstopp ohne Kursdaten nach {position.age_sec:.0f}s")
        return HOLD

    change_pct = position.price_change_pct

    # --- 0b) Liquiditaets-Notausgang --------------------------------------
    #
    # Der Kurs einer Bonding Curve wird aus den VIRTUELLEN Reserven gerechnet.
    # Ausgezahlt werden kann beim Verkauf aber hoechstens das ECHTE SOL, das in
    # der Kurve liegt. Beides laeuft auseinander, sobald eine Kurve leergezogen
    # wird: der angezeigte Kurs steht fast still, waehrend real nichts mehr zu
    # holen ist.
    #
    # Im Betrieb waren das 9 von 115 Trades und 38 % des Gesamtverlusts -
    # Positionen mit -4.5 % Kursaenderung (eine sogar mit +5.2 %), die
    # trotzdem zu 100 % wertlos waren. Der Stop-Loss schaut nur auf den Kurs
    # und konnte deshalb nie greifen; die Position lief bis zum Zeitstopp.
    #
    # Deshalb wird hier geprueft, wie viel vom rechnerischen Wert der Position
    # ueberhaupt noch auszahlbar ist. Normale Reibung (Gebuehr + Slippage)
    # ergibt rund 0.92; faellt die Deckung unter `min_liquidity_coverage`,
    # ist die Kurve leer und die Position muss sofort raus.
    # Beide Werte kommen aus DEMSELBEN Kurvenzustand - sonst vergleicht man
    # einen alten Kurs mit einer neuen Auszahlung und bekommt Unsinn.
    brutto_laut_kurs = position.tokens * state.price_sol
    if brutto_laut_kurs > 0:
        auszahlbar = position.current_token_value(cfg, state)
        deckung = auszahlbar / brutto_laut_kurs
        if deckung < cfg.advanced.min_liquidity_coverage:
            return ExitDecision(
                "close", ExitReason.LIQUIDITY,
                detail=f"Kurve leer: nur {deckung * 100:.0f}% des Kurswerts "
                       f"auszahlbar ({auszahlbar:.4f} SOL)")

    # --- 1) Rug: Absturz innerhalb eines einzigen Ticks --------------------
    if tick_drop_pct >= cfg.rug_exit_drop_per_tick_pct:
        return ExitDecision(
            "close", ExitReason.RUG,
            detail=f"-{tick_drop_pct:.1f}% in einem Tick")

    # --- 2) Stop-Loss ------------------------------------------------------
    if change_pct <= -cfg.stop_loss_pct:
        return ExitDecision(
            "close", ExitReason.STOP_LOSS,
            detail=f"{change_pct:+.1f}% <= -{cfg.stop_loss_pct}%")

    # --- 3) Take-Profit ----------------------------------------------------
    # Erst der volle TP (hoehere Schwelle), dann der Teilverkauf.
    if change_pct >= cfg.take_profit_pct:
        return ExitDecision(
            "close", ExitReason.TAKE_PROFIT,
            detail=f"{change_pct:+.1f}% >= +{cfg.take_profit_pct}%")

    if (not position.partial_done
            and cfg.partial_take_profit_size > 0
            and change_pct >= cfg.partial_take_profit_pct):
        return ExitDecision(
            "partial", ExitReason.PARTIAL_TP,
            fraction=cfg.partial_take_profit_size,
            detail=f"{change_pct:+.1f}% >= +{cfg.partial_take_profit_pct}% "
                   f"-> {cfg.partial_take_profit_size:.0%} verkaufen")

    # --- 4) Trailing-Stop --------------------------------------------------
    # Wird scharfgeschaltet, sobald der Kurs einmal ueber
    # `trailing_activate_pct` lag; danach wird ab `trailing_distance_pct`
    # unter dem Hoch verkauft.
    if change_pct >= cfg.trailing_activate_pct:
        position.trailing_active = True

    if position.trailing_active:
        drawdown = position.drawdown_from_peak_pct
        if drawdown >= cfg.trailing_distance_pct:
            return ExitDecision(
                "close", ExitReason.TRAILING,
                detail=f"-{drawdown:.1f}% vom Hoch (Limit {cfg.trailing_distance_pct}%)")

    # --- 5) Net-Sell-Flip: Kaufdruck kippt in Verkaufsdruck ----------------
    if cfg.exit_on_net_sell_flip:
        threshold = -abs(cfg.advanced.net_sell_flip_threshold_sol)
        if net_flow_sol <= threshold:
            return ExitDecision(
                "close", ExitReason.NET_SELL_FLIP,
                detail=f"{net_flow_sol:+.2f} SOL Nettoabfluss in "
                       f"{cfg.advanced.net_sell_flip_window_sec:.0f}s")

    # --- 5b) Stillstand: es passiert einfach nichts mehr ------------------
    #
    # Ersetzt den frueher sehr kurzen Zeitstopp. Ein Laeufer soll laufen
    # duerfen - aber eine Position, die nach anderthalb Minuten immer noch im
    # selben engen Band um den Einstieg pendelt, ist totes Kapital und
    # blockiert einen der Positionsplaetze.
    stagnation_after = cfg.advanced.stagnation_after_sec
    if stagnation_after > 0 and position.age_sec >= stagnation_after:
        band = abs(cfg.advanced.stagnation_band_pct)
        if abs(change_pct) <= band:
            return ExitDecision(
                "close", ExitReason.STAGNATION,
                detail=f"seit {position.age_sec:.0f}s nur {change_pct:+.1f}% "
                       f"(Band +/-{band:.0f}%)")

    # --- 6) Harter Zeitstopp ----------------------------------------------
    # Das letzte Wort. Der Bot haelt nie laenger als hard_time_stop_sec.
    if position.age_sec >= cfg.hard_time_stop_sec:
        return ExitDecision(
            "close", ExitReason.TIME_STOP,
            detail=f"Haltedauer {position.age_sec:.0f}s >= "
                   f"{cfg.hard_time_stop_sec:.0f}s")

    return HOLD
