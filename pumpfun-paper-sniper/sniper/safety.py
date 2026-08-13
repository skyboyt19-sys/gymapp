"""
safety.py -- Sicherheitsnetz fuer den reinen Simulationsbetrieb.

Dieses Modul enthaelt keine Handelslogik. Es sorgt nur dafuer, dass der
"nur Paper-Trading"-Charakter des Bots nicht aus Versehen verwaesserst wird:

1. `assert_paper_only()` prueft beim Start, dass in der Umgebung (.env oder
   Windows-Umgebungsvariablen) KEIN Private Key / keine Seed Phrase liegt.
   Falls doch, bricht der Bot ab - lieber gar nicht starten, als dass sich
   jemand darauf verlaesst, dass "der Bot das schon nicht anfasst".

2. `assert_read_only_rpc_method()` wird vom RPC-Client fuer jede Anfrage
   aufgerufen. Nur lesende Methoden sind erlaubt. Wuerde jemand (oder eine
   spaetere Aenderung) versuchen, eine Transaktion zu senden, fliegt hier
   sofort ein Fehler.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# 1) Verbotene Umgebungsvariablen
# ---------------------------------------------------------------------------
# Namensbestandteile, die auf ein echtes Wallet-Geheimnis hindeuten. Wenn eine
# Umgebungsvariable so heisst UND einen Wert hat, verweigert der Bot den Start.
_SECRET_NAME_FRAGMENTS = (
    "PRIVATE_KEY",
    "PRIVKEY",
    "SECRET_KEY",
    "SEED_PHRASE",
    "MNEMONIC",
    "KEYPAIR",
    "WALLET_KEY",
    "SOLANA_KEY",
)

# ---------------------------------------------------------------------------
# 2) Erlaubte RPC-Methoden (ausschliesslich lesend)
# ---------------------------------------------------------------------------
ALLOWED_RPC_METHODS = frozenset(
    {
        "getAccountInfo",
        "getMultipleAccounts",
        "getHealth",
        "getSlot",
        "getVersion",
    }
)


class SafetyViolation(RuntimeError):
    """Wird geworfen, wenn die Simulations-Garantie verletzt wuerde."""


def find_wallet_secrets_in_env() -> list[str]:
    """
    Sucht in den Umgebungsvariablen nach etwas, das wie ein Wallet-Geheimnis
    aussieht. Gibt die Namen der gefundenen Variablen zurueck (nie die Werte -
    die werden bewusst nirgends geloggt oder ausgegeben).
    """
    found: list[str] = []
    for name, value in os.environ.items():
        if not value or not value.strip():
            continue  # leere Variablen sind harmlos
        upper = name.upper()
        if any(fragment in upper for fragment in _SECRET_NAME_FRAGMENTS):
            found.append(name)
    return sorted(found)


def assert_paper_only() -> None:
    """
    Startpruefung. Bricht mit `SafetyViolation` ab, wenn in der Umgebung ein
    Wallet-Geheimnis liegt.

    Hintergrund: Dieser Bot soll nie in die Naehe von echtem Geld kommen. Wenn
    auf dem Rechner ein Key in der .env liegt, ist das ein Zeichen dafuer, dass
    hier vorher ein echter Trading-Bot lief - dann wird lieber gestoppt und der
    Nutzer informiert.
    """
    secrets = find_wallet_secrets_in_env()
    if secrets:
        raise SafetyViolation(
            "Abbruch aus Sicherheitsgruenden.\n"
            "In der Umgebung (.env oder Windows-Umgebungsvariablen) wurden "
            "Variablen gefunden, die nach einem Wallet-Geheimnis aussehen:\n"
            + "\n".join(f"  - {name}" for name in secrets)
            + "\n\nDieser Bot ist ein reiner Simulator und darf niemals in der "
            "Naehe eines echten Keys laufen.\n"
            "Bitte entferne diese Eintraege aus deiner .env (bzw. aus den "
            "Windows-Umgebungsvariablen) und starte erneut."
        )


def assert_read_only_rpc_method(method: str) -> None:
    """
    Wird vor JEDEM RPC-Call aufgerufen. Laesst nur lesende Methoden durch.

    Damit ist ausgeschlossen, dass dieser Bot - auch nach spaeteren
    Code-Aenderungen - versehentlich eine Transaktion an das Netzwerk schickt.
    """
    if method not in ALLOWED_RPC_METHODS:
        raise SafetyViolation(
            f"RPC-Methode '{method}' ist blockiert. "
            "Dieser Bot darf ausschliesslich lesende Aufrufe machen "
            f"(erlaubt: {', '.join(sorted(ALLOWED_RPC_METHODS))})."
        )


# Text, der beim Start gross im Terminal steht - damit nie ein Zweifel
# aufkommt, in welchem Modus das Programm laeuft.
PAPER_TRADING_BANNER = (
    "PAPER-TRADING - reine Simulation. Kein echtes Geld, keine Wallet, "
    "keine echten Transaktionen."
)
