"""
main.py -- Einstiegspunkt des Bots.

Start unter Windows:  Doppelklick auf run.bat
Start von Hand:       python -m sniper.main

Zwei Betriebsarten, gesteuert ueber `live_trading` in der config.yaml:

  live_trading: false  -> SIMULATION (Standard)
      Es wird nichts gekauft und nichts verkauft. Der Bot rechnet alles gegen
      ein virtuelles Guthaben.

  live_trading: true   -> ECHTGELD
      Kaeufe und Verkaeufe gehen ueber die PumpPortal-Lightning-API an die
      dort hinterlegte Bot-Wallet. Es wird echtes Geld bewegt.

In BEIDEN Faellen liegt kein Private Key auf diesem Rechner - der Bot signiert
grundsaetzlich nichts selbst.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import signal
import sys
from contextlib import AsyncExitStack
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
from .keep_awake import KeepAwake
from .live_engine import LiveEngine
from .market import MarketLoop
from .paper_engine import PaperEngine
from .pumpportal_trade import PumpPortalTrader
from .rpc import SolanaReadOnlyRpc
from .safety import (
    PAPER_TRADING_BANNER,
    SafetyViolation,
    assert_no_private_keys,
)

console = Console()
log = logging.getLogger("sniper")


class StartupAborted(RuntimeError):
    """Der Start wurde vor dem ersten echten Trade abgebrochen."""


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

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)

    return dashboard_handler


# ---------------------------------------------------------------------------
# Startbildschirm
# ---------------------------------------------------------------------------
def print_startup(cfg: Config) -> None:
    """Zeigt die wichtigsten Einstellungen, bevor der Bot loslegt."""
    table = Table.grid(padding=(0, 3))
    table.add_column(justify="left", style="grey70")
    table.add_column(justify="left", style="bold")

    if cfg.live_trading:
        table.add_row("Betriebsart", "[bold red]ECHTGELD[/]")
        table.add_row("Bot-Wallet", _shorten(cfg.bot_wallet_pubkey))
    else:
        table.add_row("Betriebsart", "[bold green]SIMULATION[/]")
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

    if cfg.live_trading:
        table.add_row("Slippage-Limit (Order)", f"{cfg.live.order_slippage_pct:.0f} %")
        table.add_row("Priority Fee", f"{cfg.live.priority_fee_sol:.5f} SOL pro Auftrag")
        if cfg.live.max_total_loss_pct > 0:
            table.add_row("Not-Aus bei",
                          f"-{cfg.live.max_total_loss_pct:.0f} % vom Startkapital")
        else:
            table.add_row("Not-Aus", "[red]ausgeschaltet[/]")

    table.add_row("Protokoll", f"{cfg.trades_csv_path.name} / {cfg.session_log_path.name}")

    if cfg.live_trading:
        console.print(Panel(
            Text("ECHTGELD-MODUS - es wird mit echtem Geld gehandelt.",
                 style="bold white on red"),
            border_style="red"))
    else:
        console.print(Panel(Text(PAPER_TRADING_BANNER, style="bold yellow"),
                            border_style="yellow"))

    console.print(Panel(table, title="Konfiguration", border_style="cyan"))

    if not cfg.live_trading and \
            cfg.max_open_positions * cfg.position_size_sol > cfg.start_balance_sol:
        console.print(
            "[yellow]Hinweis:[/] max_open_positions x position_size_sol ist "
            "groesser als das Startguthaben. Der Bot kauft dann einfach "
            "weniger Positionen gleichzeitig - das ist kein Fehler.\n"
        )


def _shorten(pubkey: str) -> str:
    """Adresse gekuerzt anzeigen (sie ist nicht geheim, nur lang)."""
    return f"{pubkey[:6]}...{pubkey[-4:]}" if len(pubkey) > 12 else pubkey


def _mask_rpc_url(url: str) -> str:
    """Kuerzt die RPC-URL, damit ein API-Key nicht im Klartext am Bildschirm steht."""
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
    console.print(Panel(table, title="Abschluss der Sitzung", border_style="green"))
    console.print(
        f"[grey70]Alle Trades im Detail: {engine.cfg.trades_csv_path.name}"
        f"  |  Protokoll: {engine.cfg.session_log_path.name}[/]\n"
    )


# ---------------------------------------------------------------------------
# Echtgeld: Vorpruefung und Countdown
# ---------------------------------------------------------------------------
async def prepare_live_engine(
    cfg: Config, rpc: SolanaReadOnlyRpc, stack: AsyncExitStack,
    stop_event: asyncio.Event,
) -> LiveEngine:
    """
    Prueft vor dem ersten echten Trade, ob alles stimmt, zeigt eine
    Zusammenfassung und laesst dem Nutzer Zeit zum Abbrechen.
    """
    console.print("[cyan]Pruefe Bot-Wallet ...[/]")

    balance = await rpc.get_sol_balance(cfg.bot_wallet_pubkey)
    if balance is None:
        raise StartupAborted(
            "Der Kontostand der Bot-Wallet konnte nicht abgefragt werden.\n"
            "Moegliche Ursachen: falsche BOT_WALLET_PUBKEY in der .env, oder "
            "die RPC antwortet nicht.\n"
            "Ohne Kontostand startet der Bot nicht - er koennte weder Fills "
            "pruefen noch den Not-Aus ausloesen."
        )

    needed = cfg.position_size_sol + cfg.live.min_wallet_balance_sol
    if balance < needed:
        raise StartupAborted(
            f"Zu wenig SOL auf der Bot-Wallet.\n"
            f"  Vorhanden : {balance:.4f} SOL\n"
            f"  Benoetigt : {needed:.4f} SOL "
            f"(ein Einsatz von {cfg.position_size_sol:.4f} + "
            f"{cfg.live.min_wallet_balance_sol:.4f} Gebuehrenreserve)\n\n"
            f"Bitte SOL auf {_shorten(cfg.bot_wallet_pubkey)} senden."
        )

    max_exposure = cfg.max_open_positions * cfg.position_size_sol
    loss_limit = balance * (1 - cfg.live.max_total_loss_pct / 100.0)

    warning = Table.grid(padding=(0, 3))
    warning.add_column(style="grey70")
    warning.add_column(style="bold")
    warning.add_row("Bot-Wallet", _shorten(cfg.bot_wallet_pubkey))
    warning.add_row("Guthaben jetzt", f"{balance:.4f} SOL")
    warning.add_row("Einsatz pro Trade", f"{cfg.position_size_sol:.4f} SOL")
    warning.add_row("Max. gleichzeitig im Markt",
                    f"{max_exposure:.4f} SOL ({cfg.max_open_positions} Positionen)")
    warning.add_row("Max. Trades pro Minute", str(cfg.max_snipes_per_min))
    if cfg.live.max_total_loss_pct > 0:
        warning.add_row("Not-Aus greift bei",
                        f"{loss_limit:.4f} SOL "
                        f"(-{cfg.live.max_total_loss_pct:.0f} %)")
    warning.add_row("Kosten pro Runde (ca.)",
                    f"~3 % Gebuehren + Slippage + "
                    f"{2 * cfg.live.priority_fee_sol:.4f} SOL Priority Fee")

    console.print()
    console.print(Panel(
        warning,
        title="[bold white on red] GLEICH WIRD MIT ECHTEM GELD GEHANDELT [/]",
        border_style="red"))

    # --- Countdown: letzte Gelegenheit zum Abbrechen ---
    seconds = max(0, cfg.live.startup_countdown_sec)
    if seconds:
        console.print()
        for remaining in range(seconds, 0, -1):
            console.print(
                f"  [bold red]Start in {remaining} Sekunde(n)[/] - "
                f"[yellow]STRG+C zum Abbrechen[/]",
                end="\r")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=1.0)
                raise StartupAborted("Abgebrochen.")
            except asyncio.TimeoutError:
                pass
        console.print(" " * 70, end="\r")

    trader = await stack.enter_async_context(PumpPortalTrader(
        cfg.pumpportal_api_key,
        slippage_pct=cfg.live.order_slippage_pct,
        priority_fee_sol=cfg.live.priority_fee_sol,
    ))

    engine = LiveEngine(cfg, trader, rpc, cfg.bot_wallet_pubkey, balance)
    engine.stop_event = stop_event
    log.info("ECHTGELD-Modus gestartet. Wallet %s, Guthaben %.4f SOL.",
             _shorten(cfg.bot_wallet_pubkey), balance)
    return engine


# ---------------------------------------------------------------------------
# Hauptprogramm
# ---------------------------------------------------------------------------
async def run_bot(cfg: Config, verbose: bool) -> None:
    """Startet alle Aufgaben und wartet auf das Ende (STRG+C)."""
    dashboard_handler = setup_logging(cfg, verbose)
    log.info("Bot gestartet (%s).",
             "ECHTGELD" if cfg.live_trading else "Simulation")

    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)

    queue: asyncio.Queue[NewTokenEvent] = asyncio.Queue(maxsize=5000)
    feed = PumpPortalFeed(cfg, queue)

    async with AsyncExitStack() as stack:
        # Solange der Bot laeuft, darf Windows nicht einschlafen. Im
        # Echtgeld-Modus wuerde das offene Positionen ohne Stop-Loss und ohne
        # Zeitstopp zuruecklassen.
        stack.enter_context(KeepAwake(cfg.advanced.prevent_sleep))

        rpc = await stack.enter_async_context(SolanaReadOnlyRpc(cfg))

        engine: PaperEngine
        if cfg.live_trading:
            try:
                engine = await prepare_live_engine(cfg, rpc, stack, stop_event)
            except StartupAborted as exc:
                console.print(Panel(str(exc), title="Start abgebrochen",
                                    border_style="red"))
                return
        else:
            engine = PaperEngine(cfg)

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
                    with contextlib.suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(stop_event.wait(),
                                               timeout=1.0 / refresh)
        except KeyboardInterrupt:
            stop_event.set()
        finally:
            stop_event.set()

        if cfg.live_trading:
            console.print("\n[bold yellow]Beende ... VERKAUFE offene Positionen. "
                          "Fenster bitte offen lassen![/]")
        else:
            console.print("\n[yellow]Beende ... schliesse offene Positionen.[/]")

        # Im Echtgeld-Modus grosszuegiger Timeout: hier haengen echte Verkaeufe
        # dran, die auf Blockchain-Bestaetigungen warten.
        timeout = 120.0 if cfg.live_trading else 20.0
        try:
            await asyncio.wait_for(market.close_all_positions(), timeout=timeout)
        except asyncio.TimeoutError:
            log.error("Zeitueberschreitung beim Schliessen der Positionen.")
            if cfg.live_trading and engine.positions:
                console.print(Panel(
                    "Diese Positionen konnten nicht mehr verkauft werden und "
                    "liegen noch auf der Bot-Wallet:\n\n"
                    + "\n".join(f"  {p.symbol}   {p.mint}"
                                for p in engine.positions.values())
                    + "\n\nBitte auf pump.fun mit der Bot-Wallet von Hand "
                      "verkaufen.",
                    title="[bold red]ACHTUNG[/]", border_style="red"))
        except Exception as exc:  # noqa: BLE001
            log.exception("Fehler beim Schliessen der Positionen: %s", exc)

        for task in (feed_task, market_task):
            task.cancel()
        await asyncio.gather(feed_task, market_task, return_exceptions=True)

    log.info("Bot beendet. Guthaben: %.4f SOL", engine.balance_sol)
    print_summary(engine)

    if isinstance(engine, LiveEngine) and engine.emergency_stop:
        console.print(Panel(engine.emergency_reason,
                            title="[bold red]NOT-AUS wurde ausgeloest[/]",
                            border_style="red"))


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
            pass


def main() -> NoReturn:
    """Kommandozeilen-Einstieg."""
    parser = argparse.ArgumentParser(
        prog="pumpfun-sniper",
        description="pump.fun Sniper-Bot. Standardmaessig reine Simulation; "
                    "Echtgeld nur, wenn live_trading in der config.yaml auf "
                    "true steht.",
    )
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="ausfuehrliches Protokoll (Debug-Meldungen)")
    parser.add_argument("--config", default=None,
                        help="Pfad zu einer anderen config.yaml")
    parser.add_argument("--paper", action="store_true",
                        help="erzwingt die Simulation, egal was in der "
                             "config.yaml steht")
    args = parser.parse_args()

    # --- 1) Sicherheitscheck: nie ein Private Key auf diesem Rechner ---
    try:
        assert_no_private_keys()
    except SafetyViolation as exc:
        console.print(Panel(str(exc), title="Sicherheitsabbruch", border_style="red"))
        sys.exit(2)

    # --- 2) Konfiguration ---
    try:
        cfg = load_config(Path(args.config) if args.config else None)
        if args.paper and cfg.live_trading:
            from dataclasses import replace
            cfg = replace(cfg, live_trading=False)
            console.print("[yellow]--paper gesetzt: Echtgeld-Modus wird "
                          "ignoriert, es wird simuliert.[/]\n")
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
