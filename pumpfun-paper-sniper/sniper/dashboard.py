"""
dashboard.py -- das Live-Dashboard in der Konsole (mit `rich`).

Das Bild wird mehrmals pro Sekunde neu gezeichnet und zeigt:

  * oben:   Hinweis, dass es sich um eine reine Simulation handelt
  * Konto:  virtuelles Guthaben, Gesamtwert, P&L in SOL und %, Trefferquote
  * Zaehler: gescannt / gesnipet / geskippt, Status von Feed und RPC
  * Mitte:  alle offenen Positionen mit Live-P&L und Restzeit bis zum Zeitstopp
  * unten:  die zuletzt geschlossenen Trades und die letzten Log-Zeilen

Das Dashboard liest nur - es trifft keine Entscheidungen und aendert nichts.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime

from rich.console import Group
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .config import Config
from .curve import CurveState
from .feed import PumpPortalFeed
from .market import MarketLoop
from .paper_engine import PaperEngine
from .safety import PAPER_TRADING_BANNER


class DashboardLogHandler(logging.Handler):
    """
    Faengt Log-Meldungen ab und haelt die letzten N Zeilen im Speicher, damit
    das Dashboard sie unten anzeigen kann.

    Das ist noetig, weil `rich.live` den Bildschirm staendig neu zeichnet -
    normale print()- oder Konsolen-Logausgaben wuerden das Layout zerreissen.
    Die vollstaendigen Logs landen weiterhin in der session.log.
    """

    def __init__(self, capacity: int = 200) -> None:
        super().__init__()
        self.records: deque[tuple[str, int, str]] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
            self.records.append((timestamp, record.levelno, record.getMessage()))
        except Exception:  # noqa: BLE001 - Logging darf nie etwas kaputt machen
            pass


def _pnl_style(value: float) -> str:
    """Farbe je nach Vorzeichen: gruen = Gewinn, rot = Verlust."""
    if value > 0:
        return "bold green"
    if value < 0:
        return "bold red"
    return "white"


class Dashboard:
    """Baut das Layout. `render()` liefert das jeweils aktuelle Bild."""

    def __init__(
        self,
        cfg: Config,
        engine: PaperEngine,
        market: MarketLoop,
        feed: PumpPortalFeed,
        log_handler: DashboardLogHandler,
    ) -> None:
        self.cfg = cfg
        self.engine = engine
        self.market = market
        self.feed = feed
        self.log_handler = log_handler

    # ------------------------------------------------------------------
    def render(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(self._header(), name="header", size=3),
            Layout(self._account_panel(), name="account", size=6),
            Layout(self._open_positions_panel(), name="open", ratio=2),
            Layout(self._closed_trades_panel(), name="closed", ratio=2),
            Layout(self._log_panel(), name="log",
                   size=self.cfg.advanced.dashboard_max_log_rows + 2),
        )
        return layout

    # ------------------------------------------------------------------
    def _header(self) -> Panel:
        title = Text()
        if self.cfg.live_trading:
            title.append("  pump.fun SNIPER  ", style="bold white on red")
            title.append("   ")
            title.append("ECHTGELD - es wird echtes Geld gehandelt.",
                         style="bold red")
            engine = self.engine
            if getattr(engine, "emergency_stop", False):
                title.append("   NOT-AUS AKTIV", style="bold white on red")
            return Panel(title, border_style="red")

        title.append("  pump.fun SNIPER  ", style="bold white on dark_green")
        title.append("   ")
        title.append(PAPER_TRADING_BANNER, style="bold yellow")
        return Panel(title, border_style="green")

    # ------------------------------------------------------------------
    def _account_panel(self) -> Panel:
        states: dict[str, CurveState | None] = self.market.last_states
        equity = self.engine.equity_sol(states)
        pnl_sol = equity - self.engine.start_balance_sol
        pnl_pct = (
            pnl_sol / self.engine.start_balance_sol * 100.0
            if self.engine.start_balance_sol else 0.0
        )

        table = Table.grid(padding=(0, 2))
        table.add_column(justify="left")
        table.add_column(justify="right")
        table.add_column(justify="left")
        table.add_column(justify="right")
        table.add_column(justify="left")
        table.add_column(justify="right")

        table.add_row(
            "Wallet-Guthaben" if self.cfg.live_trading else "Guthaben (frei)",
            f"{self.engine.balance_sol:.4f} SOL",
            "Gescannt", str(self.engine.tokens_scanned),
            "Feed", self._feed_status(),
        )
        table.add_row(
            "Gesamtwert", f"{equity:.4f} SOL",
            "Gesnipet", str(self.engine.tokens_sniped),
            "RPC", self._rpc_status(),
        )
        table.add_row(
            "P&L gesamt",
            Text(f"{pnl_sol:+.4f} SOL ({pnl_pct:+.2f} %)", style=_pnl_style(pnl_sol)),
            "Geskippt", str(self.engine.tokens_skipped),
            "Trades", str(len(self.engine.closed_trades)),
        )
        table.add_row(
            "Trefferquote", f"{self.engine.win_rate_pct:.1f} %",
            "Offen", f"{len(self.engine.positions)}/{self.cfg.max_open_positions}",
            "Beobachtet", str(len(self.market.candidates)),
        )

        titel = "Bot-Wallet (ECHTES GELD)" if self.cfg.live_trading \
            else "Konto (virtuell)"
        return Panel(table, title=titel,
                     border_style="red" if self.cfg.live_trading else "cyan")

    def _feed_status(self) -> Text:
        if self.feed.connected:
            return Text(f"verbunden ({self.feed.events_accepted} Token)",
                        style="green")
        return Text(f"getrennt - Reconnect laeuft ({self.feed.last_error[:30]})",
                    style="red")

    def _rpc_status(self) -> Text:
        stats = self.market.rpc.stats
        if stats.consecutive_errors == 0:
            return Text(f"ok ({stats.last_latency_ms:.0f} ms)", style="green")
        style = "yellow" if stats.consecutive_errors < 5 else "red"
        return Text(f"{stats.consecutive_errors} Fehler in Folge", style=style)

    # ------------------------------------------------------------------
    def _open_positions_panel(self) -> Panel:
        table = Table(expand=True, box=None, pad_edge=False)
        table.add_column("Ticker", style="bold", no_wrap=True)
        table.add_column("Alter", justify="right")
        table.add_column("Einstieg", justify="right")
        table.add_column("Kurs", justify="right")
        table.add_column("Kurs %", justify="right")
        table.add_column("P&L %", justify="right")
        table.add_column("bis Stop", justify="right")
        table.add_column("Status", no_wrap=True)

        if not self.engine.positions:
            table.add_row("-", "-", "-", "-", "-", "-", "-", "warte auf Signal")

        for position in self.engine.positions.values():
            state = self.market.last_states.get(position.bonding_curve)
            pnl_pct = position.unrealized_pnl_pct(self.cfg, state)
            remaining = max(0.0, self.cfg.hard_time_stop_sec - position.age_sec)

            flags = []
            if position.partial_done:
                flags.append("TeilTP")
            if position.trailing_active:
                flags.append("Trail")
            if state is not None and not state.is_tradable:
                flags.append("MIGRIERT")

            table.add_row(
                position.symbol,
                f"{position.age_sec:.0f}s",
                f"{position.entry_price:.9f}",
                f"{position.last_price:.9f}",
                Text(f"{position.price_change_pct:+.1f}%",
                     style=_pnl_style(position.price_change_pct)),
                Text(f"{pnl_pct:+.1f}%", style=_pnl_style(pnl_pct)),
                Text(f"{remaining:.0f}s",
                     style="red" if remaining < 20 else "white"),
                ", ".join(flags) or "-",
            )

        return Panel(table, title="Offene Positionen", border_style="magenta")

    # ------------------------------------------------------------------
    def _closed_trades_panel(self) -> Panel:
        table = Table(expand=True, box=None, pad_edge=False)
        table.add_column("Zeit", no_wrap=True)
        table.add_column("Ticker", style="bold", no_wrap=True)
        table.add_column("Grund", no_wrap=True)
        table.add_column("Dauer", justify="right")
        table.add_column("P&L SOL", justify="right")
        table.add_column("P&L %", justify="right")

        recent = self.engine.closed_trades[-self.cfg.advanced.dashboard_max_closed_rows:]
        if not recent:
            table.add_row("-", "-", "-", "-", "-", "-")

        for trade in reversed(recent):
            table.add_row(
                # In Ortszeit umrechnen. Intern wird UTC gefuehrt (so bleibt die
                # trades.csv eindeutig), aber in der Anzeige stand die
                # Trade-Liste damit in einer anderen Zeitzone als die
                # Ereignis-Zeilen darunter - fuer denselben Moment zwei
                # verschiedene Uhrzeiten.
                trade.closed_wall.astimezone().strftime("%H:%M:%S"),
                trade.symbol,
                _reason_text(trade.exit_reason),
                f"{trade.hold_sec:.0f}s",
                Text(f"{trade.pnl_sol:+.4f}", style=_pnl_style(trade.pnl_sol)),
                Text(f"{trade.pnl_pct:+.1f}%", style=_pnl_style(trade.pnl_sol)),
            )

        return Panel(table, title="Letzte geschlossene Trades", border_style="blue")

    # ------------------------------------------------------------------
    def _log_panel(self) -> Panel:
        rows = list(self.log_handler.records)[-self.cfg.advanced.dashboard_max_log_rows:]
        lines = []
        for timestamp, level, message in rows:
            style = "red" if level >= logging.WARNING else "grey70"
            lines.append(Text(f"{timestamp}  {message[:160]}", style=style))
        if not lines:
            lines.append(Text("Bot laeuft ... (Beenden mit STRG+C)", style="grey50"))
        return Panel(Group(*lines), title="Ereignisse", border_style="grey35")


def _reason_text(reason: str) -> Text:
    """Faerbt den Ausstiegsgrund passend ein."""
    colors = {
        "TP": "green",
        "PARTIAL": "green",
        "TRAIL": "cyan",
        "SL": "red",
        "RUG": "bold red",
        "LIQ": "bold red",
        "TIME": "yellow",
        "FLAU": "grey70",
        "FLIP": "yellow",
        "MIGR": "magenta",
        "SHUTDOWN": "grey70",
    }
    return Text(reason, style=colors.get(reason, "white"))
