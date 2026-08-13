"""
pumpportal_trade.py -- Handelsauftraege an die PumpPortal "Lightning"-API.

DAS IST DAS EINZIGE MODUL IM PROJEKT, DAS ECHTES GELD BEWEGT.
Es wird nur benutzt, wenn in der config.yaml `live_trading: true` steht.

Wie die Lightning-API funktioniert
----------------------------------
Du legst auf https://pumpportal.fun/ eine Bot-Wallet an und bekommst dafuer
einen API-Key. Die Wallet gehoert zu diesem Key; PumpPortal signiert und
sendet die Transaktionen fuer dich.

Das heisst konkret:
  * Auf deinem PC liegt **kein Private Key**. Nur der API-Key.
  * Der Bot kann ausschliesslich das bewegen, was auf dieser einen Bot-Wallet
    liegt. Deine Haupt-Wallet ist nicht erreichbar.
  * Wer den API-Key hat, kann ueber diese Wallet handeln - behandle ihn wie
    ein Passwort und lade nur so viel auf die Wallet, wie du verlieren kannst.

Endpunkt und Format (geprueft im August 2026):
    POST https://pumpportal.fun/api/trade?api-key=DEIN_KEY
    {
      "action": "buy" | "sell",
      "mint": "<Token-Adresse>",
      "amount": 0.15 | "100%",     # Zahl = Menge, "x%" = Anteil der Bestaende
      "denominatedInSol": "true",  # "true" = amount ist SOL, "false" = Token
      "slippage": 15,              # erlaubte Abweichung in Prozent
      "priorityFee": 0.0005,       # SOL, hoeher = schneller im Block
      "pool": "pump"
    }
Antwort: JSON mit "signature" (Transaktions-ID) - oder eine Fehlermeldung.

PumpPortal nimmt 0,5 % Gebuehr pro Trade, zusaetzlich zu den 1 % von pump.fun.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

log = logging.getLogger(__name__)

#: Endpunkt der Lightning-API (signiert serverseitig).
TRADE_ENDPOINT = "https://pumpportal.fun/api/trade"


@dataclass(frozen=True)
class TradeResult:
    """Ergebnis eines Handelsauftrags."""

    ok: bool
    signature: str = ""      # Transaktions-ID auf Solana (bei Erfolg)
    error: str = ""          # Klartext-Fehler (bei Misserfolg)
    http_status: int = 0

    @property
    def solscan_url(self) -> str:
        """Link zum Nachschauen im Blockchain-Explorer."""
        return f"https://solscan.io/tx/{self.signature}" if self.signature else ""


class PumpPortalTrader:
    """
    Duenner Client fuer die Lightning-API.

    Bewusst minimal gehalten: eine Methode zum Kaufen, eine zum Verkaufen.
    Es gibt hier keine Retry-Schleife - ein fehlgeschlagener Snipe wird NICHT
    automatisch wiederholt. Beim Sniping ist eine Wiederholung Sekunden spaeter
    ein voellig anderer (meist schlechterer) Trade, und jeder Versuch kostet
    Gebuehren. Der Aufrufer entscheidet, was passiert.
    """

    def __init__(
        self,
        api_key: str,
        *,
        slippage_pct: float,
        priority_fee_sol: float,
        timeout_sec: float = 20.0,
        pool: str = "pump",
    ) -> None:
        if not api_key:
            raise ValueError("PumpPortal-API-Key fehlt.")
        self._api_key = api_key
        self.slippage_pct = slippage_pct
        self.priority_fee_sol = priority_fee_sol
        self.pool = pool
        self._timeout = timeout_sec
        self._client: httpx.AsyncClient | None = None

        # Zaehler fuers Dashboard
        self.orders_sent: int = 0
        self.orders_failed: int = 0
        self.last_error: str = ""

    async def __aenter__(self) -> "PumpPortalTrader":
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout),
            headers={"Content-Type": "application/json"},
        )
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    async def buy(self, mint: str, sol_amount: float) -> TradeResult:
        """
        Kauft fuer `sol_amount` SOL den Token `mint`.
        `denominatedInSol="true"` heisst: die Menge ist in SOL angegeben.
        """
        return await self._send({
            "action": "buy",
            "mint": mint,
            "amount": sol_amount,
            "denominatedInSol": "true",
            "slippage": self.slippage_pct,
            "priorityFee": self.priority_fee_sol,
            "pool": self.pool,
        })

    async def sell_percent(self, mint: str, percent: float) -> TradeResult:
        """
        Verkauft `percent` Prozent der im Wallet liegenden Token.

        Prozent statt absoluter Mengen ist hier deutlich robuster: der Bot muss
        nicht raten, wie viele Token nach Gebuehren tatsaechlich angekommen
        sind - PumpPortal rechnet das gegen den echten Kontostand.
        `denominatedInSol="false"` heisst: die Menge bezieht sich auf Token.
        """
        percent = max(1.0, min(100.0, percent))
        # Ganze Prozent - die API erwartet Strings wie "50%" oder "100%".
        amount = f"{percent:.0f}%"
        return await self._send({
            "action": "sell",
            "mint": mint,
            "amount": amount,
            "denominatedInSol": "false",
            "slippage": self.slippage_pct,
            "priorityFee": self.priority_fee_sol,
            "pool": self.pool,
        })

    # ------------------------------------------------------------------
    async def _send(self, payload: dict[str, Any]) -> TradeResult:
        """
        Schickt den Auftrag ab und wertet die Antwort aus.

        Wirft nie eine Exception nach oben - ein fehlgeschlagener Auftrag darf
        den Bot nicht abschiessen, waehrend andere Positionen offen sind.
        """
        if self._client is None:
            return TradeResult(False, error="Trader wurde nicht gestartet.")

        self.orders_sent += 1
        # Der API-Key steht nur in der URL und wird nie geloggt.
        url = f"{TRADE_ENDPOINT}?api-key={self._api_key}"

        try:
            response = await self._client.post(url, json=payload)
        except httpx.TimeoutException:
            self.orders_failed += 1
            self.last_error = "Zeitueberschreitung"
            log.error("Auftrag %s %s: Zeitueberschreitung. Achtung: die "
                      "Transaktion kann trotzdem durchgegangen sein - der Bot "
                      "prueft gleich den echten Kontostand.",
                      payload["action"], payload["mint"][:8])
            return TradeResult(False, error="Zeitueberschreitung")
        except Exception as exc:  # noqa: BLE001
            self.orders_failed += 1
            self.last_error = f"{type(exc).__name__}"
            log.error("Auftrag fehlgeschlagen (Netzwerk): %s", exc)
            return TradeResult(False, error=f"Netzwerkfehler: {exc}")

        # --- Antwort auswerten ---
        if response.status_code != 200:
            self.orders_failed += 1
            detail = _safe_error_text(response)
            self.last_error = f"HTTP {response.status_code}"
            log.error("Auftrag %s abgelehnt (HTTP %d): %s",
                      payload["action"], response.status_code, detail)
            return TradeResult(False, error=detail, http_status=response.status_code)

        try:
            data = response.json()
        except ValueError:
            self.orders_failed += 1
            self.last_error = "unlesbare Antwort"
            return TradeResult(False, error="Antwort war kein JSON",
                               http_status=response.status_code)

        # Erfolg: {"signature": "..."}
        signature = ""
        if isinstance(data, dict):
            signature = str(data.get("signature") or "")
            if not signature and data.get("errors"):
                self.orders_failed += 1
                detail = str(data["errors"])
                self.last_error = detail[:60]
                log.error("Auftrag abgelehnt: %s", detail)
                return TradeResult(False, error=detail, http_status=200)

        if not signature:
            self.orders_failed += 1
            self.last_error = "keine Signatur"
            log.error("Auftrag ohne Signatur beantwortet: %s", str(data)[:200])
            return TradeResult(False, error="Antwort enthielt keine Signatur",
                               http_status=200)

        log.info("Auftrag %s gesendet: %s", payload["action"], signature)
        return TradeResult(True, signature=signature, http_status=200)


def _safe_error_text(response: httpx.Response) -> str:
    """Fehlertext aus der Antwort ziehen, ohne dabei selbst zu scheitern."""
    try:
        data = response.json()
        if isinstance(data, dict):
            for key in ("error", "errors", "message"):
                if key in data:
                    return str(data[key])[:200]
        return str(data)[:200]
    except Exception:  # noqa: BLE001
        return (response.text or "")[:200]
