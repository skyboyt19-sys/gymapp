"""
paper_engine.py -- das virtuelle Konto und die Buchhaltung.

Hier passiert das "Trading": Kaeufe und Verkaeufe werden ueber die
Bonding-Curve-Mathematik aus curve.py durchgerechnet und als reine Buchung
gegen ein virtuelles SOL-Guthaben gefuehrt.

Es gibt in dieser Datei - und im gesamten Projekt - keine Verbindung zu einer
echten Wallet. Ein "Kauf" ist eine Zeile in einer Liste, sonst nichts.

Buchhaltungslogik (bewusst simpel und nachvollziehbar):
  * `sol_spent`    = alles, was fuer diese Position vom Guthaben abging
                     (Einsatz + simulierte Priority Fee beim Einstieg)
  * `sol_received` = alles, was zurueckkam (Verkaufserloese abzueglich der
                     Priority Fees der Verkaeufe)
  * Gewinn/Verlust = sol_received - sol_spent
So stimmt das Guthaben am Ende exakt mit der Summe aller Trades ueberein.
"""

from __future__ import annotations

import csv
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .config import Config
from .curve import CurveState, simulate_buy, simulate_sell

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ausstiegsgruende (erscheinen im Dashboard und in der trades.csv)
# ---------------------------------------------------------------------------
class ExitReason:
    RUG = "RUG"              # Kurssturz innerhalb eines Ticks
    STOP_LOSS = "SL"         # Stop-Loss
    TAKE_PROFIT = "TP"       # voller Take-Profit
    PARTIAL_TP = "PARTIAL"   # Teilverkauf
    TRAILING = "TRAIL"       # Trailing-Stop
    NET_SELL_FLIP = "FLIP"   # Kaufdruck ist in Nettoverkaeufe gekippt
    STAGNATION = "FLAU"      # Kurs bewegt sich nicht mehr - Kapital freimachen
    LIQUIDITY = "LIQ"        # Kurve leergezogen: Kurs steht, Auszahlung fehlt
    TIME_STOP = "TIME"       # harter Zeitstopp
    MIGRATED = "MIGR"        # Token ist zu PumpSwap migriert
    SHUTDOWN = "SHUTDOWN"    # Bot wurde beendet (Strg+C)


@dataclass(frozen=True)
class EntrySnapshot:
    """
    Die Messwerte, mit denen der Einstieg begruendet wurde.

    Wandert unveraendert in die trades.csv. Ohne diese Zahlen laesst sich
    hinterher nicht auswerten, was Gewinner von Verlierern unterscheidet -
    man sieht nur, DASS ein Trade schieflief, nicht unter welchen Bedingungen
    er eroeffnet wurde.
    """

    progress_pct: float = 0.0     # Curve-Progress beim Kauf
    net_buy_sol: float = 0.0      # gemessener Kaufdruck im Signalfenster
    momentum_pct: float = 0.0     # Kursgewinn im Signalfenster
    dev_holding_pct: float = 0.0  # Anteil des Erstellers


@dataclass
class Position:
    """Eine offene Paper-Position."""

    mint: str
    symbol: str
    name: str
    bonding_curve: str

    tokens: float                # noch gehaltene Token
    tokens_initial: float        # urspruenglich gekaufte Menge
    entry_price: float           # effektiver Einstiegspreis in SOL/Token
                                 # (inkl. Gebuehr + Slippage - also das, was
                                 #  du wirklich bezahlt hast)
    sol_spent: float             # Abfluss vom Guthaben (Einsatz + Priority Fee)
    sol_received: float = 0.0    # bisherige Rueckfluesse (z.B. Teilverkauf)

    opened_at: float = field(default_factory=time.monotonic)   # fuer Zeitmessung
    opened_wall: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc))    # fuer die CSV

    last_price: float = 0.0      # zuletzt gesehener Kurs
    peak_price: float = 0.0      # hoechster Kurs seit Einstieg (fuer Trailing)
    partial_done: bool = False   # Teilverkauf schon erfolgt?
    trailing_active: bool = False

    #: Womit der Einstieg begruendet wurde - fuer die Auswertung in trades.csv
    entry_snapshot: EntrySnapshot = field(default_factory=EntrySnapshot)

    #: Wie oft in diesen Token schon gekauft wurde (1 = nur der Ersteinstieg).
    #: Nachkaeufe erhoehen `tokens` und `sol_spent` derselben Position; der
    #: Einstiegspreis wird zum gewichteten Mittel. Eine Position pro Token zu
    #: fuehren haelt die Ausstiegslogik einfach - es gibt nur einen Verkauf.
    entries: int = 1

    #: True, solange ein echter Handelsauftrag zu dieser Position unterwegs
    #: ist. Verhindert, dass der Bot denselben Verkauf mehrfach ausloest,
    #: waehrend die erste Order noch bestaetigt wird. Im Simulationsmodus
    #: immer False, weil dort alles sofort passiert.
    pending: bool = False

    # -- abgeleitete Werte -------------------------------------------------
    @property
    def age_sec(self) -> float:
        """Wie lange die Position schon offen ist (Sekunden)."""
        return time.monotonic() - self.opened_at

    @property
    def price_change_pct(self) -> float:
        """
        Kursveraenderung gegenueber dem effektiven Einstiegspreis, in Prozent.
        Das ist der Wert, gegen den take_profit_pct / stop_loss_pct pruefen.
        """
        if self.entry_price <= 0:
            return 0.0
        return (self.last_price / self.entry_price - 1.0) * 100.0

    @property
    def drawdown_from_peak_pct(self) -> float:
        """Wie weit der Kurs unter seinem Hoch seit Einstieg liegt (Prozent)."""
        if self.peak_price <= 0:
            return 0.0
        return (1.0 - self.last_price / self.peak_price) * 100.0

    def current_token_value(self, cfg: Config, state: CurveState | None) -> float:
        """
        Was brächte der Restbestand, wenn wir ihn jetzt sofort verkaufen?

        Rechnet den Verkauf real durch die Kurve (inkl. Gebuehr und Slippage),
        damit die Anzeige nicht schoener ist als die tatsaechliche Ausfuehrung.
        Liefert die Kurve keinen Kurs mehr (migriert / RPC-Aussetzer), wird zum
        zuletzt gesehenen Kurs bewertet - dieselbe Regel wie beim Schliessen.
        """
        if self.tokens <= 0:
            return 0.0

        if state is not None and state.is_tradable:
            try:
                quote = simulate_sell(
                    state, self.tokens,
                    fee_pct=cfg.fee_pct, slippage_pct=cfg.slippage_pct,
                )
                return max(0.0, quote.sol_out - cfg.simulated_priority_fee_sol)
            except Exception:  # noqa: BLE001 - Anzeige darf nie crashen
                return 0.0

        gross = self.tokens * self.last_price * (1.0 - cfg.slippage_pct / 100.0)
        return max(0.0, gross * (1.0 - cfg.fee_pct / 100.0)
                   - cfg.simulated_priority_fee_sol)

    def unrealized_pnl_sol(self, cfg: Config, state: CurveState | None) -> float:
        """Gewinn/Verlust, wenn wir die Position jetzt sofort schliessen wuerden."""
        return self.sol_received + self.current_token_value(cfg, state) - self.sol_spent

    def unrealized_pnl_pct(self, cfg: Config, state: CurveState | None) -> float:
        """Derselbe Wert wie oben, aber in Prozent des Einsatzes."""
        if self.sol_spent <= 0:
            return 0.0
        return self.unrealized_pnl_sol(cfg, state) / self.sol_spent * 100.0


@dataclass
class ClosedTrade:
    """Ein abgeschlossener Trade - fuer Dashboard, CSV und Endabrechnung."""

    symbol: str
    mint: str
    exit_reason: str
    entry_price: float
    exit_price: float
    sol_spent: float
    sol_received: float
    pnl_sol: float
    pnl_pct: float
    hold_sec: float
    opened_wall: datetime
    closed_wall: datetime
    had_partial: bool


class PaperEngine:
    """
    Virtuelles Konto + Positionsverwaltung.

    Alle Methoden sind synchron; die Aufrufe kommen aus der Poll-Schleife in
    market.py. Dadurch kann es keine Race Conditions auf dem Guthaben geben.
    """

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.balance_sol: float = cfg.start_balance_sol
        self.start_balance_sol: float = cfg.start_balance_sol

        self.positions: dict[str, Position] = {}   # mint -> Position
        self.closed_trades: list[ClosedTrade] = []

        # -- Zaehler fuer das Dashboard --
        self.tokens_scanned: int = 0    # Launches gesehen
        self.tokens_sniped: int = 0     # gekauft
        self.tokens_skipped: int = 0    # Filter nicht bestanden
        self.total_fees_sol: float = 0.0

        # -- Rate-Limit: Zeitstempel der letzten Kaeufe (fuer max_snipes_per_min)
        self._recent_snipes: list[float] = []

        self._csv_path: Path = cfg.trades_csv_path
        self._ensure_csv_header()

    # ------------------------------------------------------------------
    # Kennzahlen
    # ------------------------------------------------------------------
    @property
    def realized_pnl_sol(self) -> float:
        """Gewinn/Verlust aus allen bereits geschlossenen Positionen."""
        return sum(trade.pnl_sol for trade in self.closed_trades)

    @property
    def realized_pnl_pct(self) -> float:
        if self.start_balance_sol <= 0:
            return 0.0
        return self.realized_pnl_sol / self.start_balance_sol * 100.0

    @property
    def win_rate_pct(self) -> float:
        """Anteil der geschlossenen Trades mit Gewinn, in Prozent."""
        if not self.closed_trades:
            return 0.0
        wins = sum(1 for trade in self.closed_trades if trade.pnl_sol > 0)
        return wins / len(self.closed_trades) * 100.0

    def equity_sol(self, states: dict[str, CurveState | None]) -> float:
        """
        Gesamtwert des virtuellen Kontos: freies Guthaben plus der aktuelle
        Verkaufswert aller offenen Positionen.
        `states` ist die Zuordnung Bonding-Curve-Adresse -> aktueller Zustand.
        """
        total = self.balance_sol
        for position in self.positions.values():
            total += position.current_token_value(
                self.cfg, states.get(position.bonding_curve))
        return total

    # ------------------------------------------------------------------
    # Kauf
    # ------------------------------------------------------------------
    def can_open(self) -> tuple[bool, str]:
        """
        Prueft die "harten" Grenzen vor einem Kauf: Anzahl offener Positionen,
        Guthaben und das Snipes-pro-Minute-Limit.
        Rueckgabe: (darf kaufen?, Begruendung falls nein)
        """
        if len(self.positions) >= self.cfg.max_open_positions:
            return False, f"max_open_positions ({self.cfg.max_open_positions}) erreicht"

        needed = self.cfg.position_size_sol + self.cfg.simulated_priority_fee_sol
        if self.balance_sol < needed:
            return False, (f"Guthaben zu klein ({self.balance_sol:.4f} SOL, "
                           f"benoetigt {needed:.4f} SOL)")

        # Gleitendes Ein-Minuten-Fenster
        now = time.monotonic()
        self._recent_snipes = [t for t in self._recent_snipes if now - t < 60.0]
        if len(self._recent_snipes) >= self.cfg.max_snipes_per_min:
            return False, f"max_snipes_per_min ({self.cfg.max_snipes_per_min}) erreicht"

        return True, ""

    def open_position(
        self,
        *,
        mint: str,
        symbol: str,
        name: str,
        bonding_curve: str,
        state: CurveState,
        snapshot: EntrySnapshot | None = None,
    ) -> Position | None:
        """
        Simuliert den Kauf und legt die Position an.
        Gibt None zurueck, wenn der Kauf nicht moeglich ist (die Begruendung
        landet im Log).
        """
        if mint in self.positions:
            return None  # doppelt kaufen wollen wir nicht

        allowed, reason = self.can_open()
        if not allowed:
            log.info("Kauf %s abgelehnt: %s", symbol, reason)
            return None

        try:
            quote = simulate_buy(
                state,
                self.cfg.position_size_sol,
                fee_pct=self.cfg.fee_pct,
                slippage_pct=self.cfg.slippage_pct,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Kauf %s nicht simulierbar: %s", symbol, exc)
            return None

        # --- Buchung ---
        priority_fee = self.cfg.simulated_priority_fee_sol
        sol_spent = quote.sol_in + priority_fee
        self.balance_sol -= sol_spent
        self.total_fees_sol += quote.fee_sol + priority_fee

        position = Position(
            mint=mint,
            symbol=symbol,
            name=name,
            bonding_curve=bonding_curve,
            tokens=quote.tokens_out,
            tokens_initial=quote.tokens_out,
            # Effektiver Einstiegspreis: inkl. Gebuehr, Slippage und Priority
            # Fee. Ein Take-Profit von +40% bedeutet damit wirklich +40% auf
            # das, was du bezahlt hast.
            entry_price=sol_spent / quote.tokens_out,
            sol_spent=sol_spent,
            last_price=state.price_sol,
            peak_price=state.price_sol,
            entry_snapshot=snapshot or EntrySnapshot(),
        )
        self.positions[mint] = position
        self.tokens_sniped += 1
        self._recent_snipes.append(time.monotonic())

        log.info(
            "KAUF %s | %.4f SOL -> %.0f Token | Einstieg %.10f SOL "
            "| Spot %.10f | Guthaben %.4f SOL",
            symbol, sol_spent, quote.tokens_out, position.entry_price,
            quote.spot_price_before, self.balance_sol,
        )
        self._write_csv_row(position, event="OPEN", reason="ENTRY",
                            price=position.entry_price, sol_flow=-sol_spent,
                            tokens=quote.tokens_out, pnl_sol=0.0, pnl_pct=0.0)
        return position

    def add_to_position(self, position: Position, state: CurveState) -> bool:
        """
        Kauft in eine bereits offene Position nach ("Pyramiding").

        Es entsteht KEINE zweite Position: Menge und Einsatz werden derselben
        Position zugeschlagen, der Einstiegspreis wird zum gewichteten Mittel.
        Damit bleibt die Ausstiegslogik unveraendert - es gibt weiterhin genau
        einen Verkauf pro Token.

        Achtung, das ist die riskanteste Funktion im Programm: Sie haeuft
        Kapital in EINEM Token an. Geht er hoch, gewinnst du mehrfach; ruggt
        er, verlierst du mehrfach. Deshalb greifen davor gleich mehrere
        Bremsen (max_entries_per_token, pyramid_min_gain_pct, Guthaben).
        """
        if position.entries >= self.cfg.advanced.max_entries_per_token:
            return False

        needed = self.cfg.position_size_sol + self.cfg.simulated_priority_fee_sol
        if self.balance_sol < needed:
            return False

        try:
            quote = simulate_buy(
                state, self.cfg.position_size_sol,
                fee_pct=self.cfg.fee_pct, slippage_pct=self.cfg.slippage_pct,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Nachkauf %s nicht simulierbar: %s", position.symbol, exc)
            return False

        priority_fee = self.cfg.simulated_priority_fee_sol
        sol_spent = quote.sol_in + priority_fee
        self.balance_sol -= sol_spent
        self.total_fees_sol += quote.fee_sol + priority_fee

        position.tokens += quote.tokens_out
        position.tokens_initial += quote.tokens_out
        position.sol_spent += sol_spent
        position.entries += 1
        # Gewichteter Mittelwert: alles Bezahlte geteilt durch alles Erhaltene.
        position.entry_price = position.sol_spent / position.tokens_initial

        log.info("NACHKAUF %s (%d. Einstieg) | %.4f SOL -> %.0f Token | "
                 "neuer Mittelwert %.10f SOL | Guthaben %.4f SOL",
                 position.symbol, position.entries, sol_spent,
                 quote.tokens_out, position.entry_price, self.balance_sol)

        self._write_csv_row(position, event="ADD", reason="PYRAMID",
                            price=state.price_sol, sol_flow=-sol_spent,
                            tokens=quote.tokens_out, pnl_sol=0.0, pnl_pct=0.0)
        return True

    def request_add(self, position: Position, state: CurveState) -> None:
        """Nachkauf - in der Simulation sofort ausgefuehrt."""
        self.add_to_position(position, state)

    # ------------------------------------------------------------------
    # Verkauf
    # ------------------------------------------------------------------
    def partial_sell(
        self, position: Position, state: CurveState, fraction: float, reason: str
    ) -> float:
        """
        Verkauft einen Teil der Position (z.B. 50 % beim Teil-Take-Profit).
        Gibt das erhaltene SOL zurueck. Die Position bleibt offen.
        """
        fraction = max(0.0, min(1.0, fraction))
        tokens_to_sell = position.tokens * fraction
        if tokens_to_sell <= 0:
            return 0.0

        sol_out = self._execute_sell(position, state, tokens_to_sell)
        position.partial_done = True

        log.info(
            "TEILVERKAUF %s (%s) | %.0f Token -> %.4f SOL | Rest %.0f Token",
            position.symbol, reason, tokens_to_sell, sol_out, position.tokens,
        )
        self._write_csv_row(
            position, event="PARTIAL", reason=reason,
            price=state.price_sol, sol_flow=sol_out, tokens=tokens_to_sell,
            pnl_sol=0.0, pnl_pct=0.0,
        )
        return sol_out

    def close_position(
        self, position: Position, state: CurveState | None, reason: str
    ) -> ClosedTrade:
        """
        Schliesst die Position vollstaendig und schreibt sie in die Historie.

        `state` darf None sein (RPC antwortet gerade nicht) oder eine bereits
        migrierte Kurve enthalten. In beiden Faellen laesst sich der Verkauf
        nicht mehr ueber die Bonding Curve rechnen - dann wird der Restbestand
        zum zuletzt gesehenen Kurs bewertet (siehe `_settle_at_last_price`).
        """
        sol_out = 0.0
        exit_price = position.last_price

        if state is not None and state.is_tradable and position.tokens > 0:
            sol_out = self._execute_sell(position, state, position.tokens)
            exit_price = state.price_sol
        elif position.tokens > 0:
            sol_out = self._settle_at_last_price(position)
        else:
            position.tokens = 0.0

        pnl_sol = position.sol_received - position.sol_spent
        pnl_pct = (pnl_sol / position.sol_spent * 100.0) if position.sol_spent else 0.0

        trade = ClosedTrade(
            symbol=position.symbol,
            mint=position.mint,
            exit_reason=reason,
            entry_price=position.entry_price,
            exit_price=exit_price,
            sol_spent=position.sol_spent,
            sol_received=position.sol_received,
            pnl_sol=pnl_sol,
            pnl_pct=pnl_pct,
            hold_sec=position.age_sec,
            opened_wall=position.opened_wall,
            closed_wall=datetime.now(timezone.utc),
            had_partial=position.partial_done,
        )
        self.closed_trades.append(trade)
        self.positions.pop(position.mint, None)

        log.info(
            "VERKAUF %s (%s) | %.4f SOL zurueck | P&L %+.4f SOL (%+.1f%%) "
            "| Haltedauer %.0fs | Guthaben %.4f SOL",
            position.symbol, reason, sol_out, pnl_sol, pnl_pct,
            trade.hold_sec, self.balance_sol,
        )
        self._write_csv_row(
            position, event="CLOSE", reason=reason,
            price=exit_price, sol_flow=sol_out, tokens=trade.sol_received,
            pnl_sol=pnl_sol, pnl_pct=pnl_pct,
        )
        return trade

    def _settle_at_last_price(self, position: Position) -> float:
        """
        Bewertet den Restbestand zum zuletzt gesehenen Kurs.

        Wird gebraucht, wenn die Bonding Curve keinen Kurs mehr liefert:
          * Der Token ist zu PumpSwap MIGRIERT. Das ist der Erfolgsfall des
            Tokens - die Kurve ist voll, der Kurs auf ihrem Hoechststand. Die
            Token waeren auf PumpSwap weiterhin verkaeuflich. Sie mit 0 zu
            bewerten waere schlicht falsch und wuerde die Statistik verzerren.
          * Die RPC liefert gerade keine Daten. Dann ist der letzte gesehene
            Kurs die beste verfuegbare Schaetzung.

        Gebuehr und Slippage werden trotzdem abgezogen, damit die Bewertung
        nicht zu optimistisch ausfaellt. Ist nie ein Kurs gesehen worden
        (last_price = 0), ergibt das folgerichtig 0 SOL.
        """
        gross = position.tokens * position.last_price
        after_slippage = gross * (1.0 - self.cfg.slippage_pct / 100.0)
        fee = after_slippage * (self.cfg.fee_pct / 100.0)
        net = max(0.0, after_slippage - fee - self.cfg.simulated_priority_fee_sol)

        position.tokens = 0.0
        position.sol_received += net
        self.balance_sol += net
        self.total_fees_sol += fee + self.cfg.simulated_priority_fee_sol
        return net

    def _execute_sell(
        self, position: Position, state: CurveState, tokens: float
    ) -> float:
        """
        Gemeinsame Verkaufsmechanik fuer Teil- und Komplettverkauf:
        Kurve durchrechnen, Priority Fee abziehen, Konto gutschreiben.
        """
        tokens = min(tokens, position.tokens)
        if tokens <= 0:
            return 0.0

        try:
            quote = simulate_sell(
                state, tokens,
                fee_pct=self.cfg.fee_pct, slippage_pct=self.cfg.slippage_pct,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Verkauf %s nicht simulierbar: %s", position.symbol, exc)
            return 0.0

        priority_fee = self.cfg.simulated_priority_fee_sol
        # Netto-Gutschrift; nie unter 0 (die Priority Fee kann den Erloes bei
        # einem wertlosen Token uebersteigen - dann ist der Erloes eben 0).
        net_in = max(0.0, quote.sol_out - priority_fee)

        position.tokens -= tokens
        position.sol_received += net_in
        self.balance_sol += net_in
        self.total_fees_sol += quote.fee_sol + priority_fee
        return net_in

    # ------------------------------------------------------------------
    # Einheitliche Schnittstelle fuer die Markt-Schleife
    # ------------------------------------------------------------------
    # Die Markt-Schleife (market.py) soll nicht wissen muessen, ob simuliert
    # oder echt gehandelt wird. Deshalb ruft sie nur diese drei Methoden auf.
    # Im Simulationsmodus passiert alles sofort; im Echtgeld-Modus (live_engine)
    # wird daraus ein Auftrag im Hintergrund.

    def request_open(self, *, mint: str, symbol: str, name: str,
                     bonding_curve: str, state: CurveState,
                     snapshot: EntrySnapshot | None = None) -> None:
        """Kaufauftrag - in der Simulation sofort ausgefuehrt."""
        self.open_position(mint=mint, symbol=symbol, name=name,
                           bonding_curve=bonding_curve, state=state,
                           snapshot=snapshot)

    def request_exit(self, position: Position, state: CurveState | None,
                     *, fraction: float, reason: str) -> None:
        """
        Verkaufsauftrag. `fraction < 1.0` bedeutet Teilverkauf.
        In der Simulation sofort ausgefuehrt.
        """
        if fraction >= 1.0 or state is None:
            self.close_position(position, state, reason)
        else:
            self.partial_sell(position, state, fraction, reason)

    def is_busy(self, mint: str) -> bool:
        """
        Laeuft gerade ein Auftrag zu diesem Token? In der Simulation nie -
        dort gibt es keine Wartezeit zwischen Entscheidung und Ausfuehrung.
        """
        return False

    def check_emergency_stop(
        self, states: dict[str, CurveState | None] | None = None
    ) -> None:
        """
        Verlustgrenze pruefen. In der Simulation gibt es keinen Not-Aus -
        es kann ja nichts verloren gehen. Die Methode existiert nur, damit die
        Markt-Schleife beide Betriebsarten gleich behandeln kann.
        """
        return

    async def shutdown(self, states: dict[str, CurveState | None]) -> None:
        """Beim Beenden alle offenen Positionen schliessen."""
        for position in list(self.positions.values()):
            try:
                self.close_position(
                    position, states.get(position.bonding_curve),
                    ExitReason.SHUTDOWN)
            except Exception as exc:  # noqa: BLE001
                log.exception("Position %s konnte nicht geschlossen werden: %s",
                              position.symbol, exc)

    # ------------------------------------------------------------------
    # Kursaktualisierung
    # ------------------------------------------------------------------
    def update_position_price(self, position: Position, price: float) -> None:
        """Merkt sich den neuen Kurs und zieht das Hoch (fuer Trailing) nach."""
        if price > 0:
            position.last_price = price
            if price > position.peak_price:
                position.peak_price = price

    # ------------------------------------------------------------------
    # CSV-Protokoll
    # ------------------------------------------------------------------
    CSV_HEADER = [
        "zeit_utc", "event", "grund", "symbol", "mint",
        "preis_sol", "sol_fluss", "token", "einstieg_sol", "haltedauer_sek",
        "pnl_sol", "pnl_pct", "guthaben_sol",
        # Womit der Einstieg begruendet wurde - erst damit laesst sich
        # auswerten, unter welchen Bedingungen Trades funktionieren.
        "progress_pct", "kaufdruck_sol", "momentum_pct", "dev_anteil_pct",
    ]

    def _ensure_csv_header(self) -> None:
        """
        Legt trades.csv an, falls sie fehlt.

        Stammt eine vorhandene Datei noch von einer aelteren Version mit
        anderen Spalten, wird sie zur Seite gelegt statt weiterbeschrieben -
        sonst stuenden in einer Datei Zeilen mit unterschiedlich vielen
        Spalten, und die Auswertung waere unbrauchbar.
        """
        try:
            if self._csv_path.exists():
                with self._csv_path.open("r", encoding="utf-8") as handle:
                    erste_zeile = handle.readline().strip()
                if erste_zeile and erste_zeile.split(";") != self.CSV_HEADER:
                    stempel = datetime.now().strftime("%Y%m%d_%H%M%S")
                    alt = self._csv_path.with_name(
                        f"{self._csv_path.stem}_alt_{stempel}.csv")
                    self._csv_path.rename(alt)
                    log.info("trades.csv hatte ein aelteres Spaltenformat und "
                             "wurde nach %s umbenannt.", alt.name)
                else:
                    return

            with self._csv_path.open("w", newline="", encoding="utf-8") as handle:
                csv.writer(handle, delimiter=";").writerow(self.CSV_HEADER)
        except OSError as exc:
            log.warning("trades.csv konnte nicht angelegt werden: %s", exc)

    def _write_csv_row(
        self, position: Position, *, event: str, reason: str,
        price: float, sol_flow: float, tokens: float,
        pnl_sol: float, pnl_pct: float,
    ) -> None:
        """
        Haengt eine Zeile an trades.csv an.

        Trennzeichen ist ";" - so oeffnet Excel unter Windows die Datei direkt
        korrekt in Spalten, ohne Import-Assistent.
        """
        try:
            with self._csv_path.open("a", newline="", encoding="utf-8") as handle:
                csv.writer(handle, delimiter=";").writerow([
                    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    event,
                    reason,
                    position.symbol,
                    position.mint,
                    f"{price:.12f}",
                    f"{sol_flow:.6f}",
                    f"{tokens:.4f}",
                    f"{position.entry_price:.12f}",
                    f"{position.age_sec:.1f}",
                    f"{pnl_sol:.6f}",
                    f"{pnl_pct:.2f}",
                    f"{self.balance_sol:.6f}",
                    f"{position.entry_snapshot.progress_pct:.2f}",
                    f"{position.entry_snapshot.net_buy_sol:.4f}",
                    f"{position.entry_snapshot.momentum_pct:.2f}",
                    f"{position.entry_snapshot.dev_holding_pct:.2f}",
                ])
        except OSError as exc:
            # Datei gesperrt (z.B. in Excel geoeffnet) - kein Grund zum Absturz.
            log.warning("Schreiben in trades.csv fehlgeschlagen: %s", exc)

    # ------------------------------------------------------------------
    # Abschlussbericht
    # ------------------------------------------------------------------
    def summary_lines(self) -> list[str]:
        """Text-Zusammenfassung fuer das Ende der Sitzung."""
        wins = sum(1 for t in self.closed_trades if t.pnl_sol > 0)
        losses = len(self.closed_trades) - wins
        best = max((t.pnl_pct for t in self.closed_trades), default=0.0)
        worst = min((t.pnl_pct for t in self.closed_trades), default=0.0)
        avg_hold = (
            sum(t.hold_sec for t in self.closed_trades) / len(self.closed_trades)
            if self.closed_trades else 0.0
        )

        return [
            f"Startguthaben     : {self.start_balance_sol:.4f} SOL",
            f"Endguthaben       : {self.balance_sol:.4f} SOL",
            f"Gewinn/Verlust    : {self.realized_pnl_sol:+.4f} SOL "
            f"({self.realized_pnl_pct:+.2f} %)",
            f"Trades            : {len(self.closed_trades)}  "
            f"(Gewinne {wins} / Verluste {losses})",
            f"Trefferquote      : {self.win_rate_pct:.1f} %",
            f"Bester Trade      : {best:+.1f} %",
            f"Schlechtester     : {worst:+.1f} %",
            f"Haltedauer (Mittel): {avg_hold:.0f} Sekunden",
            f"Simulierte Gebuehren: {self.total_fees_sol:.4f} SOL",
            f"Gescannt / Gesnipet / Geskippt: "
            f"{self.tokens_scanned} / {self.tokens_sniped} / {self.tokens_skipped}",
        ]
