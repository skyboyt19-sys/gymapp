"""
main.py -- Einstiegspunkt des Bots.

Start unter Windows:  Doppelklick auf run.bat
Start von Hand:       python -m sniper.main

Ablauf:
  1. Sicherheitscheck (kein Wallet-Geheimnis in der Umgebung)
  2. Konfiguration laden und anzeigen
  3. Logging einrichten (Datei session.log + Ringpuffer fuers Dashboard)
  4. Drei Aufgaben parallel starten:
       - Feed    : haelt die WebSocket-Verbindung zu PumpPortal
       - Markt   : pollt Kurse, entscheidet Kauf/Verkauf
       - Anzeige : zeichnet das Dashboard
  5. Bei STRG+C: alle offenen Paper-Positionen schliessen und
     Abschlussbericht ausgeben
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import signal
import sys
from pathlib import Path
from typing import NoReturn

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .config import Config, ConfigError, load_config
from .dashboard import Dashboard, DashboardLogHandler
from .feed import NewTokenEvent, PumpPortalFeed
from .market import MarketLoop
from .paper_engine import PaperEngine
from .rpc import SolanaReadOnlyRpc
from .safety import PAPER_TRADING_BANNER, SafetyViolation, assert_paper_only

console = Console()
log = logging.getLogger("sniper")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def setup_logging(cfg: Config, verbose: bool) -> DashboardLogHandler:
    """
    Richtet zwei Ziele ein:
      * session.log  - vollstaendiges Protokoll auf der Festplatte
      * Ringpuffer   - die letzten Zeilen fuer die Anzeige im Dashboard

    Bewusst KEIN Handler auf die Konsole: das wuerde das Live-Dashboard
    zerschiessen.
    """
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)

    # Alte Handler entfernen (relevant beim Neustart im selben Prozess/Tests)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    file_handler = logging.FileHandler(cfg.session_log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-7s  %(name)-18s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(file_handler)

    dashboard_handler = DashboardLogHandler()
    dashboard_handler.setLevel(logging.INFO)
    root.addHandler(dashboard_handler)

    # httpx und websockets sind sehr gespraechig - auf WARNING drosseln.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)

    return dashboard_handler


# ---------------------------------------------------------------------------
# Start- und Endbildschirm
# ---------------------------------------------------------------------------
def print_startup(cfg: Config) -> None:
    """Zeigt die wichtigsten Einstellungen, bevor der Bot loslegt."""
    table = Table.grid(padding=(0, 3))
    table.add_column(justify="left", style="grey70")
    table.add_column(justify="left", style="bold")

    table.add_row("Startguthaben", f"{cfg.start_balance_sol:.4f} SOL (virtuell)")
    table.add_row("Einsatz pro Snipe", f"{cfg.position_size_sol:.4f} SOL")
    table.add_row("Max. offene Positionen", str(cfg.max_open_positions))
    table.add_row("Signalfenster", f"{cfg.signal_window_sec:.0f} s")
    table.add_row("Zwangsverkauf nach", f"{cfg.hard_time_stop_sec:.0f} s")
    table.add_row("Take-Profit / Stop-Loss",
                  f"+{cfg.take_profit_pct:.0f} % / -{cfg.stop_loss_pct:.0f} %")
    table.add_row("Kurs-Refresh", f"alle {cfg.rpc_poll_ms} ms")
    table.add_row("Feed", cfg.advanced.pumpportal_ws_url)
    table.add_row("RPC", _mask_rpc_url(cfg.rpc_url))
    table.add_row("Protokoll", f"{cfg.trades_csv_path.name} / {cfg.session_log_path.name}")

    banner = Text(PAPER_TRADING_BANNER, style="bold yellow")
    console.print(Panel(banner, border_style="yellow"))
    console.print(Panel(table, title="Konfiguration", border_style="cyan"))

    if cfg.max_open_positions * cfg.position_size_sol > cfg.start_balance_sol:
        console.print(
            "[yellow]Hinweis:[/] max_open_positions x position_size_sol ist "
            "groesser als das Startguthaben. Der Bot kauft dann einfach "
            "weniger Positionen gleichzeitig - das ist kein Fehler.\n"
        )


def _mask_rpc_url(url: str) -> str:
    """
    Kuerzt die RPC-URL fuer die Anzeige, damit ein API-Key nicht im Klartext
    auf dem Bildschirm steht (falls jemand einen Screenshot teilt).
    """
    if "api-key=" in url:
        base, _, _rest = url.partition("api-key=")
        return f"{base}api-key=***"
    if url.count("/") > 3:
        head, _, _tail = url.rpartition("/")
        return f"{head}/***"
    return url


def print_summary(engine: PaperEngine) -> None:
    """Abschlussbericht nach dem Beenden."""
    table = Table.grid(padding=(0, 3))
    table.add_column(justify="left", style="grey70")
    for line in engine.summary_lines():
        label, _, value = line.partition(":")
        table.add_row(label.strip(), value.strip())

    console.print()
    console.print(Panel(table, title="Abschluss der Sitzung (Simulation)",
                        border_style="green"))
    console.print(
        f"[grey70]Alle Trades im Detail: "
        f"{engine._csv_path.name}  |  Protokoll: session.log[/]\n"
    )


# ---------------------------------------------------------------------------
# Hauptprogramm
# ---------------------------------------------------------------------------
async def run_bot(cfg: Config, verbose: bool) -> None:
    """Startet alle Aufgaben und wartet auf das Ende (STRG+C)."""
    dashboard_handler = setup_logging(cfg, verbose)
    log.info("Bot gestartet - reiner Simulationsbetrieb.")

    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)

    # Queue zwischen Feed und Markt-Schleife. Grosszuegig dimensioniert:
    # bei einem Launch-Schub soll nichts verloren gehen.
    queue: asyncio.Queue[NewTokenEvent] = asyncio.Queue(maxsize=5000)

    engine = PaperEngine(cfg)
    feed = PumpPortalFeed(cfg, queue)

    async with SolanaReadOnlyRpc(cfg) as rpc:
        market = MarketLoop(cfg, engine, rpc, queue)
        dashboard = Dashboard(cfg, engine, market, feed, dashboard_handler)

        feed_task = asyncio.create_task(feed.run(stop_event), name="feed")
        market_task = asyncio.create_task(market.run(stop_event), name="market")

        try:
            refresh = max(1, cfg.advanced.dashboard_refresh_per_sec)
            with Live(dashboard.render(), console=console,
                      refresh_per_second=refresh, screen=False) as live:
                while not stop_event.is_set():
                    live.update(dashboard.render())
                    # Warten, aber bei STRG+C sofort reagieren.
                    with contextlib.suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(stop_event.wait(),
                                               timeout=1.0 / refresh)
        except KeyboardInterrupt:
            # Faengt STRG+C ab, falls der Signal-Handler nicht greift
            # (kommt unter Windows gelegentlich vor).
            stop_event.set()
        finally:
            stop_event.set()

        console.print("\n[yellow]Beende ... schliesse offene Paper-Positionen.[/]")

        # Positionen schliessen, solange der RPC-Client noch offen ist.
        with contextlib.suppress(Exception):
            await asyncio.wait_for(market.close_all_positions(), timeout=20.0)

        # Hintergrundaufgaben sauber beenden.
        for task in (feed_task, market_task):
            task.cancel()
        await asyncio.gather(feed_task, market_task, return_exceptions=True)

    log.info("Bot beendet. Endguthaben: %.4f SOL", engine.balance_sol)
    print_summary(engine)


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    """
    Sorgt dafuer, dass STRG+C sauber herunterfaehrt, statt mitten im Handel
    abzubrechen.

    Unter Windows kennt asyncio `add_signal_handler` nicht - dort faengt der
    KeyboardInterrupt-Block in `run_bot` bzw. `main()` den Abbruch ab.
    """
    loop = asyncio.get_running_loop()
    for signal_name in ("SIGINT", "SIGTERM"):
        signal_number = getattr(signal, signal_name, None)
        if signal_number is None:
            continue
        try:
            loop.add_signal_handler(signal_number, stop_event.set)
        except (NotImplementedError, RuntimeError):
            # Windows: nicht unterstuetzt - kein Problem, siehe Docstring.
            pass


def main() -> NoReturn:
    """Kommandozeilen-Einstieg."""
    parser = argparse.ArgumentParser(
        prog="pumpfun-paper-sniper",
        description="pump.fun Sniper-Bot im reinen Paper-Trading-Modus "
                    "(Simulation, kein echtes Geld).",
    )
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="ausfuehrliches Protokoll (Debug-Meldungen)")
    parser.add_argument("--config", default=None,
                        help="Pfad zu einer anderen config.yaml")
    args = parser.parse_args()

    # --- 1) Sicherheitscheck ---
    try:
        assert_paper_only()
    except SafetyViolation as exc:
        console.print(Panel(str(exc), title="Sicherheitsabbruch", border_style="red"))
        sys.exit(2)

    # --- 2) Konfiguration ---
    try:
        cfg = load_config(Path(args.config) if args.config else None)
    except ConfigError as exc:
        console.print(Panel(str(exc), title="Fehler in der Konfiguration",
                            border_style="red"))
        sys.exit(2)

    print_startup(cfg)

    # --- 3) Loslegen ---
    try:
        asyncio.run(run_bot(cfg, args.verbose))
    except KeyboardInterrupt:
        console.print("\n[yellow]Abgebrochen.[/]")
    except Exception as exc:  # noqa: BLE001
        log.exception("Unbehandelter Fehler: %s", exc)
        console.print(Panel(f"{type(exc).__name__}: {exc}\n\n"
                            "Details stehen in der session.log.",
                            title="Unerwarteter Fehler", border_style="red"))
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
