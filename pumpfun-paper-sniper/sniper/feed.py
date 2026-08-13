"""
feed.py -- Live-Feed der neuen pump.fun-Launches.

Datenquelle: PumpPortal WebSocket  (kostenlos, kein API-Key noetig)
    wss://pumpportal.fun/api/data
    Methode: {"method": "subscribeNewToken"}
    Doku:    https://pumpportal.fun/data-api/real-time/

Wichtige Regel von PumpPortal: **nur eine** WebSocket-Verbindung gleichzeitig
offen halten. Wer mehrere aufmacht, wird geblockt. Dieses Modul haelt genau
eine Verbindung und abonniert darueber alles, was gebraucht wird.

Was der Feed liefert (Beispiel-Event):
    {
      "signature": "...",
      "mint": "...",                    <- Adresse des neuen Tokens
      "traderPublicKey": "...",         <- der Creator ("Dev")
      "txType": "create",
      "name": "My Token",
      "symbol": "MYT",
      "uri": "https://...",
      "initialBuy": 30000000,           <- Token, die der Dev sofort gekauft hat
      "solAmount": 1.5,                 <- SOL, die der Dev dafuer eingesetzt hat
      "bondingCurveKey": "...",         <- Adresse des Bonding-Curve-Accounts
      "vTokensInBondingCurve": 1000000000,
      "vSolInBondingCurve": 31.5,
      "marketCapSol": 32.7,
      "pool": "pump"
    }

Falls PumpPortal einmal nicht erreichbar ist:
Der Feed versucht endlos, sich neu zu verbinden (mit wachsender Wartezeit).
Alternativen waeren Bitquery (pump.fun GraphQL-Streams, kostenloses Kontingent)
oder ein eigener Geyser/Yellowstone-Zugang - beides braucht aber eine
Registrierung bzw. kostet ab einem gewissen Volumen. Deshalb ist PumpPortal
hier die einzige, wirklich kostenlose Standardquelle. Siehe README.md,
Abschnitt "Wenn der Feed nicht laeuft".
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

from .config import Config

log = logging.getLogger(__name__)

#: Gesamtangebot eines pump.fun-Tokens (1 Milliarde Stueck).
TOTAL_SUPPLY_TOKENS = 1_000_000_000.0


@dataclass(frozen=True)
class NewTokenEvent:
    """Ein neu gelaunchter Token, aufbereitet aus dem Feed-Event."""

    mint: str                    # Token-Adresse
    symbol: str
    name: str
    creator: str                 # Wallet des Devs
    bonding_curve: str           # Adresse des Bonding-Curve-Accounts
    initial_buy_tokens: float    # Token, die der Dev sofort gekauft hat
    initial_buy_sol: float       # dafuer eingesetztes SOL
    v_tokens: float              # virtuelle Token-Reserve laut Feed
    v_sol: float                 # virtuelle SOL-Reserve laut Feed
    market_cap_sol: float
    pool: str
    received_at: float           # lokale Uhrzeit (time.monotonic) des Empfangs

    @property
    def initial_price_sol(self) -> float:
        """
        Startpreis direkt aus dem Event - spart den ersten RPC-Call.
        (Der Feed liefert die Reserven bereits als "ganze" Einheiten, nicht in
        Lamports/Mikroeinheiten - deshalb hier keine Umrechnung.)
        """
        if self.v_tokens <= 0:
            return 0.0
        return self.v_sol / self.v_tokens

    @property
    def dev_holding_pct(self) -> float:
        """
        Wie viel Prozent des Gesamtangebots haelt der Dev nach seinem
        Initial-Buy? Hoher Wert = der Dev kann den Kurs jederzeit alleine
        zerlegen ("Rug"). Deshalb filtert die Strategie darauf.
        """
        if TOTAL_SUPPLY_TOKENS <= 0:
            return 0.0
        return max(0.0, min(100.0, self.initial_buy_tokens / TOTAL_SUPPLY_TOKENS * 100.0))


def _to_float(value: Any, default: float = 0.0) -> float:
    """Robuste Zahlenumwandlung - der Feed schickt gelegentlich Strings oder null."""
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_token_amount(raw: float) -> float:
    """
    PumpPortal liefert Token-Mengen normalerweise als "ganze" Token
    (z.B. 30000000 = 30 Mio Stueck). Manche Endpunkte liefern aber Rohwerte in
    Mikroeinheiten (also x 1_000_000).

    Heuristik: Das Gesamtangebot sind 1 Mrd Token. Ist der Wert deutlich
    groesser, kann es sich nur um Basiseinheiten handeln -> durch 1e6 teilen.
    """
    if raw > TOTAL_SUPPLY_TOKENS * 1.5:
        return raw / 1_000_000.0
    return raw


def parse_new_token_event(payload: dict[str, Any]) -> NewTokenEvent | None:
    """
    Wandelt ein rohes Feed-Event in ein `NewTokenEvent` um.

    Gibt None zurueck, wenn das Event nichts mit einem neuen Token zu tun hat
    (z.B. die Bestaetigung des Abos) oder Pflichtfelder fehlen. Der Aufrufer
    ignoriert solche Events einfach - der Bot soll an keiner Stelle wegen einer
    unerwarteten Nachricht abstuerzen.
    """
    # Abo-Bestaetigungen sehen so aus: {"message": "Successfully subscribed..."}
    if "mint" not in payload:
        return None

    mint = str(payload.get("mint") or "").strip()
    if not mint:
        return None

    # txType ist bei Launches "create". Manche Feed-Versionen lassen das Feld
    # weg - dann akzeptieren wir das Event trotzdem.
    tx_type = str(payload.get("txType") or "create").lower()
    if tx_type not in ("create", ""):
        return None

    bonding_curve = str(payload.get("bondingCurveKey") or "").strip()

    return NewTokenEvent(
        mint=mint,
        symbol=str(payload.get("symbol") or "?")[:12],
        name=str(payload.get("name") or "")[:40],
        # Neuere Feed-Versionen nennen das Feld "creator", aeltere
        # "traderPublicKey" - beides wird unterstuetzt.
        creator=str(payload.get("creator") or payload.get("traderPublicKey") or ""),
        bonding_curve=bonding_curve,
        initial_buy_tokens=_normalize_token_amount(_to_float(payload.get("initialBuy"))),
        initial_buy_sol=_to_float(payload.get("solAmount")),
        v_tokens=_to_float(payload.get("vTokensInBondingCurve")),
        v_sol=_to_float(payload.get("vSolInBondingCurve")),
        market_cap_sol=_to_float(payload.get("marketCapSol")),
        pool=str(payload.get("pool") or "pump").lower(),
        received_at=time.monotonic(),
    )


class PumpPortalFeed:
    """
    Haelt genau eine WebSocket-Verbindung zu PumpPortal und legt jeden neuen
    Token in eine `asyncio.Queue`. Der Rest des Bots liest nur aus dieser Queue
    und muss sich um Verbindungsabbrueche nicht kuemmern.
    """

    def __init__(self, cfg: Config, queue: asyncio.Queue[NewTokenEvent]) -> None:
        self.cfg = cfg
        self.queue = queue

        # -- Statistik fuer das Dashboard --
        self.connected: bool = False
        self.connect_count: int = 0
        self.events_seen: int = 0        # alle empfangenen Launch-Events
        self.events_accepted: int = 0    # davon: passender Pool, gueltige Daten
        self.last_event_at: float | None = None
        self.last_error: str = ""

    async def run(self, stop_event: asyncio.Event) -> None:
        """
        Endlosschleife: verbinden -> lauschen -> bei Abbruch neu verbinden.
        Laeuft, bis `stop_event` gesetzt wird (Strg+C).
        """
        backoff = self.cfg.advanced.ws_reconnect_min_sec

        while not stop_event.is_set():
            try:
                await self._connect_and_listen(stop_event)
                # Sauber beendet (z.B. Server hat die Verbindung geschlossen):
                # Backoff zuruecksetzen, es lag nicht an einem Dauerproblem.
                backoff = self.cfg.advanced.ws_reconnect_min_sec

            except asyncio.CancelledError:
                raise

            except Exception as exc:  # noqa: BLE001 - der Feed darf nie sterben
                self.connected = False
                self.last_error = f"{type(exc).__name__}: {exc}"
                log.warning("Feed-Verbindung verloren (%s). Neuer Versuch in %.1fs.",
                            self.last_error, backoff)

            if stop_event.is_set():
                break

            # Warten, aber sofort abbrechen, wenn der Bot beendet wird.
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop_event.wait(), timeout=backoff)

            # Exponentielles Backoff, gedeckelt auf ws_reconnect_max_sec.
            backoff = min(backoff * 2.0, self.cfg.advanced.ws_reconnect_max_sec)

        self.connected = False
        log.info("Feed beendet.")

    async def _connect_and_listen(self, stop_event: asyncio.Event) -> None:
        """Eine Verbindung aufbauen und Nachrichten verarbeiten, bis sie abreisst."""
        url = self.cfg.advanced.pumpportal_ws_url
        log.info("Verbinde mit Feed: %s", url)

        async with websockets.connect(
            url,
            ping_interval=20,     # Keepalive: alle 20s ein Ping
            ping_timeout=20,      # ohne Pong nach 20s gilt die Verbindung als tot
            close_timeout=5,
            max_queue=1024,
        ) as ws:
            self.connected = True
            self.connect_count += 1
            self.last_error = ""
            log.info("Feed verbunden (Verbindung #%d).", self.connect_count)

            # Abo fuer neue Token. Genau ein Abo auf genau einer Verbindung.
            await ws.send(json.dumps({"method": "subscribeNewToken"}))

            while not stop_event.is_set():
                try:
                    # Timeout, damit die Schleife regelmaessig `stop_event` prueft.
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                except ConnectionClosed:
                    self.connected = False
                    raise

                self._handle_raw_message(raw)

        self.connected = False

    def _handle_raw_message(self, raw: str | bytes) -> None:
        """
        Verarbeitet eine einzelne Feed-Nachricht.

        Alles hier ist in try/except gekapselt: ein einzelnes kaputtes Event
        darf niemals den Feed - und damit den Bot - abschiessen.
        """
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            log.debug("Unlesbare Feed-Nachricht ignoriert.")
            return

        if not isinstance(payload, dict):
            return

        # Server-Hinweise (z.B. Abo-Bestaetigung) nur ins Log schreiben.
        if "mint" not in payload and "message" in payload:
            log.info("Feed-Meldung: %s", payload["message"])
            return

        try:
            event = parse_new_token_event(payload)
        except Exception as exc:  # noqa: BLE001
            log.debug("Event konnte nicht gelesen werden: %s", exc)
            return

        if event is None:
            return

        self.events_seen += 1
        self.last_event_at = time.monotonic()

        # Pool-Filter: die Bonding-Curve-Mathematik in curve.py gilt fuer
        # pump.fun. Andere Launchpads (z.B. "bonk") haben ein anderes
        # Account-Layout und werden deshalb ignoriert.
        allowed = self.cfg.advanced.allowed_pools
        if allowed and event.pool not in allowed:
            log.debug("Token %s uebersprungen (Pool '%s').", event.symbol, event.pool)
            return

        # Ohne Bonding-Curve-Adresse koennen wir den Kurs nicht verfolgen.
        if not event.bonding_curve:
            log.debug("Token %s ohne bondingCurveKey - wird verworfen.", event.symbol)
            return

        self.events_accepted += 1

        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            # Sollte praktisch nie passieren (die Queue ist gross). Falls doch:
            # lieber ein Event verlieren als den Feed blockieren.
            log.warning("Event-Queue voll - Token %s verworfen.", event.symbol)
