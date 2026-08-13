"""
pump.fun Paper-Sniper
=====================

Ein vollstaendig simulierter ("Paper Trading") Sniper-Bot fuer pump.fun.

Der Bot hoert die echten Live-Launches auf pump.fun mit und rechnet Kaeufe und
Verkaeufe gegen die realen Kursdaten der Bonding Curve durch - aber
ausschliesslich als interne Buchung gegen ein virtuelles SOL-Konto.

GARANTIE (technisch, nicht nur als Versprechen):
  * Es gibt in diesem Paket keine Bibliothek, die Transaktionen signieren kann.
  * Es gibt keine Funktion, die einen Private Key oder eine Seed Phrase
    entgegennimmt, speichert oder abfragt.
  * Alle Solana-Zugriffe sind LESEND (JSON-RPC "getMultipleAccounts").
    Es wird nie "sendTransaction" oder aehnliches aufgerufen.
"""

__version__ = "1.0.0"
