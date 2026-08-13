"""
check_feed.py -- Schritt-1-Test: laeuft der Live-Feed?

Dieses kleine Programm handelt NICHTS. Es verbindet sich nur mit PumpPortal
und schreibt jeden neuen pump.fun-Token in die Konsole. Damit siehst du in
30 Sekunden, ob der Feed auf deinem Rechner funktioniert (Internet, Firewall,
Virenscanner ...), bevor du den eigentlichen Bot startest.

Start unter Windows:
    Doppelklick auf  check_feed.bat
oder in der Eingabeaufforderung:
    .venv\\Scripts\\python.exe check_feed.py

Beenden mit STRG+C.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys

from rich.console import Console
from rich.table import Table

from sniper.config import ConfigError, load_config
from sniper.feed import NewTokenEvent, PumpPortalFeed

console = Console()


async def main() -> int:
    # Logging in die Konsole - hier gibt es kein Dashboard, das stoeren koennte.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("websockets").setLevel(logging.WARNING)

    try:
        cfg = load_config()
    except ConfigError as exc:
        console.print(f"[red]Fehler in der Konfiguration:[/] {exc}")
        return 2

    console.print(
        "[bold green]Feed-Test[/] - es wird nichts gehandelt.\n"
        f"Verbinde mit [cyan]{cfg.advanced.pumpportal_ws_url}[/]\n"
        "Beenden mit STRG+C.\n"
    )

    queue: asyncio.Queue[NewTokenEvent] = asyncio.Queue(maxsize=1000)
    feed = PumpPortalFeed(cfg, queue)
    stop_event = asyncio.Event()

    feed_task = asyncio.create_task(feed.run(stop_event))

    table = Table(title="Neue pump.fun-Token (live)")
    table.add_column("#", justify="right", style="grey70")
    table.add_column("Ticker", style="bold")
    table.add_column("Name")
    table.add_column("Startpreis SOL", justify="right")
    table.add_column("Dev-Buy SOL", justify="right")
    table.add_column("Dev-Anteil", justify="right")
    table.add_column("Mint", style="grey70")

    count = 0
    try:
        while True:
            event = await queue.get()
            count += 1
            console.print(
                f"[grey70]{count:>4}[/]  "
                f"[bold]{event.symbol:<10}[/] "
                f"{event.name[:24]:<24} "
                f"Preis {event.initial_price_sol:.10f} SOL  "
                f"Dev-Buy {event.initial_buy_sol:>6.3f} SOL  "
                f"Dev-Anteil {event.dev_holding_pct:>5.1f} %  "
                f"[grey50]{event.mint[:12]}...[/]"
            )
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        stop_event.set()
        feed_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await feed_task

    console.print(f"\n[green]Fertig.[/] {count} neue Token empfangen.")
    if count == 0:
        console.print(
            "[yellow]Es kam kein einziger Token an.[/] Moegliche Ursachen:\n"
            "  * keine Internetverbindung / Firewall blockiert WebSockets\n"
            "  * PumpPortal gerade nicht erreichbar\n"
            "  * Virenscanner blockiert Python\n"
            "Siehe README.md, Abschnitt 'Wenn der Feed nicht laeuft'."
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(0)
