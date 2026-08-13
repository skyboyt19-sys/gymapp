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

    Warum das reicht, um Kaufdruck zu messen: Jeder Kauf schiebt SOL in die
    Kurve, jeder Verkauf zieht SOL heraus. Steigt die Reserve, wird netto
    gekauft; faellt sie, wird netto verkauft. Man braucht dafuer also keinen
    (kostenpflichtigen) Trade-Stream - die Reserve-Aenderung genuegt.
    """

    def __init__(self, max_samples: int = 240) -> None:
        # (Zeitpunkt, virtuelle SOL-Reserve in Lamports)
        self._samples: deque[tuple[float, int]] = deque(maxlen=max_samples)

    def add(self, timestamp: float, virtual_sol_reserves: int) -> None:
        self._samples.append((timestamp, virtual_sol_reserves))

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
    """Ein neuer Token, der gerade beobachtet (aber noch nicht gekauft) wird."""

    event: NewTokenEvent
    #: Preis zu Beginn des Fensters (aus dem Feed-Event, spart einen RPC-Call)
    start_price: float
    #: SOL-Reserve zu Beginn des Fensters, in Lamports
    start_sol_reserves: int
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
        """Neuen Kurs-Messpunkt aufnehmen."""
        self.last_state = state
        self.ticks += 1
        price = state.price_sol
        if price > 0:
            self.last_price = price
            self.max_price = max(self.max_price, price)
        self.flow.add(now, state.virtual_sol_reserves)

    @property
    def price_gain_pct(self) -> float:
        """Kursgewinn seit Beginn des Beobachtungsfensters, in Prozent."""
        if self.start_price <= 0 or self.last_price <= 0:
            return 0.0
        return (self.last_price / self.start_price - 1.0) * 100.0

    @property
    def net_buy_volume_sol(self) -> float:
        """Netto in die Kurve geflossenes SOL seit Fensterbeginn."""
        return self.flow.total_flow_sol(self.start_sol_reserves)


def make_candidate(event: NewTokenEvent) -> Candidate:
    """
    Baut aus einem Feed-Event einen Kandidaten.

    Der Startpreis und die Start-Reserve kommen direkt aus dem Event - so
    beginnt die Messung sofort beim Launch und nicht erst beim ersten
    RPC-Poll (das waere bis zu `rpc_poll_ms` spaeter).
    """
    return Candidate(
        event=event,
        start_price=event.initial_price_sol,
        start_sol_reserves=int(event.v_sol * LAMPORTS_PER_SOL),
    )


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

    # 1) Migriert / abgeschlossen?
    if cfg.skip_if_complete and not state.is_tradable:
        return EntryDecision(False, "Token migriert (complete)")

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

    # --- 6) Harter Zeitstopp ----------------------------------------------
    # Das letzte Wort. Der Bot haelt nie laenger als hard_time_stop_sec.
    if position.age_sec >= cfg.hard_time_stop_sec:
        return ExitDecision(
            "close", ExitReason.TIME_STOP,
            detail=f"Haltedauer {position.age_sec:.0f}s >= "
                   f"{cfg.hard_time_stop_sec:.0f}s")

    return HOLD
