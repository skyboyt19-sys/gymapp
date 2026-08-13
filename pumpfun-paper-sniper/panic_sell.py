"""
panic_sell.py -- Notausgang: verkauft ALLES, was auf der Bot-Wallet liegt.

Wofuer das da ist
-----------------
Die Bot-Wallet bei PumpPortal ist eine reine API-Wallet. Du kannst sie nicht
einfach im Browser mit pump.fun verbinden und dort von Hand verkaufen. Wenn
also der Bot abgestuerzt ist, der PC ausgegangen ist oder ein Verkauf endgueltig
fehlgeschlagen ist, liegen die Token da - und du brauchst einen Weg raus.

Das ist dieser Weg.

Das Skript:
  1. fragt die Bot-Wallet ab und listet alle Token auf, die dort liegen
  2. fragt dich, ob es wirklich alles verkaufen soll
  3. verkauft nacheinander jede Position zu 100 %

Start unter Windows:  Doppelklick auf  panic_sell.bat

Es handelt nur in eine Richtung: verkaufen. Kaufen kann dieses Skript nicht.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from sniper.config import ConfigError, load_config
from sniper.pumpportal_trade import PumpPortalTrader
from sniper.rpc import SolanaReadOnlyRpc
from sniper.safety import SafetyViolation, assert_no_private_keys

console = Console()


async def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        assert_no_private_keys()
    except SafetyViolation as exc:
        console.print(Panel(str(exc), title="Sicherheitsabbruch", border_style="red"))
        return 2

    try:
        cfg = load_config()
    except ConfigError as exc:
        console.print(f"[red]Fehler in der Konfiguration:[/] {exc}")
        return 2

    # Dieses Skript braucht die Echtgeld-Zugangsdaten - unabhaengig davon, ob
    # live_trading gerade an oder aus ist. Genau dafuer ist es ja da.
    if not cfg.pumpportal_api_key or not cfg.bot_wallet_pubkey:
        console.print(Panel(
            "In der .env fehlen PUMPPORTAL_API_KEY und/oder BOT_WALLET_PUBKEY.\n"
            "Ohne die beiden kann dieses Skript die Bot-Wallet nicht erreichen.",
            title="Zugangsdaten fehlen", border_style="red"))
        return 2

    console.print(Panel(
        "[bold]NOTVERKAUF[/]\nVerkauft alle Token auf der Bot-Wallet zu 100 %.",
        border_style="yellow"))

    async with SolanaReadOnlyRpc(cfg) as rpc:
        console.print("Frage Bot-Wallet ab ...")
        sol = await rpc.get_sol_balance(cfg.bot_wallet_pubkey)
        holdings = await rpc.list_token_holdings(cfg.bot_wallet_pubkey)

        if holdings is None:
            console.print("[red]Die Wallet konnte nicht abgefragt werden.[/] "
                          "Stimmt BOT_WALLET_PUBKEY? Antwortet die RPC?")
            return 1

        console.print(f"SOL-Guthaben: [bold]{sol if sol is not None else '?'}[/]")

        if not holdings:
            console.print("\n[green]Es liegen keine Token auf der Wallet. "
                          "Nichts zu tun.[/]")
            return 0

        table = Table(title="Gefundene Token")
        table.add_column("Mint")
        table.add_column("Menge", justify="right")
        for mint, amount in holdings.items():
            table.add_row(mint, f"{amount:,.0f}")
        console.print(table)

        # --- Rueckfrage ---
        console.print("\n[bold yellow]Wirklich ALLE oben genannten Token "
                      "verkaufen?[/]")
        try:
            answer = input("Tippe JA und druecke Enter (alles andere bricht ab): ")
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer.strip().upper() != "JA":
            console.print("[yellow]Abgebrochen. Es wurde nichts verkauft.[/]")
            return 0

        # --- Verkaufen ---
        async with PumpPortalTrader(
            cfg.pumpportal_api_key,
            slippage_pct=max(cfg.live.order_slippage_pct, 25.0),  # grosszuegig:
            priority_fee_sol=cfg.live.priority_fee_sol,           # Hauptsache raus
        ) as trader:
            erfolge, fehler = 0, 0
            for mint, amount in holdings.items():
                console.print(f"\nVerkaufe {amount:,.0f} von {mint[:12]}... ")
                result = await trader.sell_percent(mint, 100.0)
                if result.ok:
                    erfolge += 1
                    console.print(f"  [green]Auftrag raus:[/] {result.solscan_url}")
                else:
                    fehler += 1
                    console.print(f"  [red]Fehlgeschlagen:[/] {result.error}")
                await asyncio.sleep(1.0)  # der RPC etwas Luft lassen

        # --- Kontrolle ---
        console.print("\nWarte 15 Sekunden und pruefe nach ...")
        await asyncio.sleep(15)
        rest = await rpc.list_token_holdings(cfg.bot_wallet_pubkey)
        sol_neu = await rpc.get_sol_balance(cfg.bot_wallet_pubkey)

        console.print(f"\nSOL-Guthaben jetzt: [bold]{sol_neu if sol_neu is not None else '?'}[/]")
        if rest:
            console.print(Panel(
                "Diese Token liegen noch auf der Wallet:\n\n"
                + "\n".join(f"  {m}  ({a:,.0f})" for m, a in rest.items())
                + "\n\nMoegliche Gruende: der Token ist zu PumpSwap migriert "
                  "(dann 'pool' anpassen), die Kurve ist leer, oder die "
                  "Slippage war zu eng.\nDu kannst das Skript einfach noch "
                  "einmal starten.",
                title="[yellow]Reste[/]", border_style="yellow"))
        else:
            console.print("[bold green]Alles verkauft. Wallet ist token-frei.[/]")

        console.print(f"\nAuftraege: {erfolge} erfolgreich, {fehler} fehlgeschlagen.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        console.print("\n[yellow]Abgebrochen.[/]")
        sys.exit(0)
