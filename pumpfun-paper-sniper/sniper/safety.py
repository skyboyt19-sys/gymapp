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
        # Kontostaende der Bot-Wallet (nur lesen). Wird im Echtgeld-Modus
        # gebraucht, um Fills und den Not-Aus zu pruefen.
        "getBalance",
        "getTokenAccountsByOwner",
        # Liest eine bereits gesendete Transaktion nach, um den exakten
        # Geldfluss zu ermitteln. Reines Nachschlagen, kein Senden.
        "getTransaction",
    }
)

#: Methoden, mit denen man eine Transaktion senden koennte. Sie stehen hier
#: nur, damit klar dokumentiert ist, dass sie NIE erlaubt sind - der Bot
#: signiert grundsaetzlich nichts selbst. Im Echtgeld-Modus laeuft das Signieren
#: bei PumpPortal (Lightning-API), nicht in diesem Programm.
FOREVER_FORBIDDEN_RPC_METHODS = frozenset(
    {
        "sendTransaction",
        "sendRawTransaction",
        "requestAirdrop",
        "simulateTransaction",
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


def assert_no_private_keys() -> None:
    """
    Startpruefung - laeuft in BEIDEN Betriebsarten (Simulation und Echtgeld).

    Dieser Bot signiert grundsaetzlich nichts selbst:
      * Im Simulationsmodus wird ueberhaupt nicht gehandelt.
      * Im Echtgeld-Modus signiert PumpPortal (Lightning-API) mit der dort
        hinterlegten Bot-Wallet. Der Bot braucht dafuer nur einen API-Key.

    In beiden Faellen gibt es also keinen Grund, warum ein Private Key oder
    eine Seed Phrase auf diesem Rechner in der Bot-Umgebung liegen sollte.
    Findet sich doch einer, wird der Start verweigert - denn dann stimmt die
    Annahme nicht mehr, unter der dieses Programm gebaut wurde.
    """
    secrets = find_wallet_secrets_in_env()
    if secrets:
        raise SafetyViolation(
            "Abbruch aus Sicherheitsgruenden.\n"
            "In der Umgebung (.env oder Windows-Umgebungsvariablen) wurden "
            "Variablen gefunden, die nach einem Wallet-Geheimnis aussehen:\n"
            + "\n".join(f"  - {name}" for name in secrets)
            + "\n\nDieser Bot braucht so etwas nie: Er signiert nichts selbst.\n"
            "Im Echtgeld-Modus uebernimmt das PumpPortal mit deinem API-Key -\n"
            "dafuer genuegt PUMPPORTAL_API_KEY in der .env.\n\n"
            "Bitte entferne die oben genannten Eintraege und starte erneut."
        )


#: Alter Name, damit bestehender Code und Tests weiter funktionieren.
assert_paper_only = assert_no_private_keys


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
