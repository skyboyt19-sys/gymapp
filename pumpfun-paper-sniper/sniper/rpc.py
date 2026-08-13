"""
rpc.py -- lesender Zugriff auf Solana, um die Bonding Curves abzufragen.

Der Bot braucht fuer jede beobachtete Position den aktuellen Kurs. Der steht im
Bonding-Curve-Account auf der Blockchain. Statt fuer jeden Token einen eigenen
Aufruf zu machen (das wuerde jede kostenlose RPC sofort ins Rate-Limit
schicken), holen wir mit `getMultipleAccounts` bis zu 100 Accounts auf einmal.

SICHERHEIT: Dieser Client kann ausschliesslich LESEN. Vor jedem Aufruf laeuft
`safety.assert_read_only_rpc_method()`. Eine Transaktion zu senden ist hier
technisch nicht moeglich.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass

import httpx

from .config import Config
from .curve import CurveState, decode_bonding_curve
from .safety import assert_read_only_rpc_method

log = logging.getLogger(__name__)


@dataclass
class RpcStats:
    """Zaehler fuer das Dashboard und zur Fehlersuche."""

    calls_ok: int = 0
    calls_failed: int = 0
    consecutive_errors: int = 0
    rate_limited: int = 0        # wie oft die RPC mit "429" geantwortet hat
    last_error: str = ""
    last_latency_ms: float = 0.0


class SolanaReadOnlyRpc:
    """
    Minimaler, rein lesender JSON-RPC-Client fuer Solana.

    Benutzung:
        async with SolanaReadOnlyRpc(cfg) as rpc:
            states = await rpc.fetch_curve_states(["Adresse1", "Adresse2"])
    """

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.stats = RpcStats()
        self._client: httpx.AsyncClient | None = None
        self._request_id = 0

    # -- Kontextmanager: oeffnet/schliesst die HTTP-Verbindung ------------
    async def __aenter__(self) -> "SolanaReadOnlyRpc":
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.cfg.advanced.rpc_timeout_sec),
            headers={"Content-Type": "application/json"},
            # Verbindungen offen halten - spart bei 800ms-Polling viel Zeit.
            limits=httpx.Limits(max_keepalive_connections=4, max_connections=8),
        )
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # -- interner Aufruf ---------------------------------------------------
    async def _call(self, method: str, params: list) -> dict:
        """
        Fuehrt einen JSON-RPC-Aufruf aus und gibt das "result"-Objekt zurueck.
        Wirft eine Exception bei Netz-, HTTP- oder RPC-Fehlern.
        """
        # >>> Sicherheitsnetz: nur lesende Methoden sind erlaubt. <<<
        assert_read_only_rpc_method(method)

        if self._client is None:
            raise RuntimeError("RPC-Client wurde nicht gestartet (async with fehlt).")

        self._request_id += 1
        body = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }

        loop = asyncio.get_running_loop()
        started = loop.time()
        response = await self._client.post(self.cfg.rpc_url, json=body)
        self.stats.last_latency_ms = (loop.time() - started) * 1000.0

        if response.status_code == 429:
            self.stats.rate_limited += 1
            raise RuntimeError(
                "RPC-Rate-Limit erreicht (HTTP 429). Tipp: kostenlosen Key von "
                "Helius/QuickNode in die .env eintragen oder rpc_poll_ms erhoehen."
            )
        response.raise_for_status()

        data = response.json()
        if "error" in data:
            raise RuntimeError(f"RPC-Fehler: {data['error']}")
        return data.get("result", {})

    # -- oeffentliche API --------------------------------------------------
    async def fetch_curve_states(
        self, addresses: list[str]
    ) -> dict[str, CurveState | None]:
        """
        Holt fuer eine Liste von Bonding-Curve-Adressen den aktuellen Zustand.

        Rueckgabe: {Adresse: CurveState}  bzw.  {Adresse: None}, wenn der
        Account nicht existiert oder sich nicht dekodieren liess.

        Fehler beim Netzwerk werden hier NICHT geschluckt - die ruft der
        Aufrufer (market.py) ab und protokolliert sie. Ein einzelner
        fehlerhafter Account fuehrt dagegen nur zu `None` fuer diese Adresse.
        """
        result: dict[str, CurveState | None] = {}
        if not addresses:
            return result

        chunk_size = max(1, self.cfg.advanced.rpc_max_accounts_per_call)

        for start in range(0, len(addresses), chunk_size):
            chunk = addresses[start:start + chunk_size]
            try:
                raw = await self._call(
                    "getMultipleAccounts",
                    [chunk, {"encoding": "base64", "commitment": "processed"}],
                )
                self.stats.calls_ok += 1
                self.stats.consecutive_errors = 0
                self.stats.last_error = ""
            except Exception as exc:  # noqa: BLE001
                self.stats.calls_failed += 1
                self.stats.consecutive_errors += 1
                self.stats.last_error = f"{type(exc).__name__}: {exc}"
                log.warning("RPC-Aufruf fehlgeschlagen: %s", self.stats.last_error)
                # Fuer diesen Block gibt es keine Daten - der Bot arbeitet mit
                # den zuletzt bekannten Kursen weiter und versucht es beim
                # naechsten Tick erneut.
                for address in chunk:
                    result.setdefault(address, None)
                continue

            accounts = raw.get("value") or []
            for address, account in zip(chunk, accounts):
                result[address] = _decode_account(address, account)

        return result


def _decode_account(address: str, account: dict | None) -> CurveState | None:
    """
    Dekodiert einen einzelnen Account aus der RPC-Antwort.

    Gibt None zurueck, wenn:
      * der Account (noch) nicht existiert - direkt nach dem Launch kann es
        einen Sekundenbruchteil dauern, bis die RPC ihn kennt,
      * die Daten nicht wie eine pump.fun Bonding Curve aussehen.
    In beiden Faellen wird nur eine Debug-Zeile geschrieben, kein Fehler.
    """
    if not account:
        return None

    try:
        data_field = account.get("data")
        # Format bei encoding=base64: ["<base64-string>", "base64"]
        if isinstance(data_field, list) and data_field:
            raw_bytes = base64.b64decode(data_field[0])
        elif isinstance(data_field, str):
            raw_bytes = base64.b64decode(data_field)
        else:
            return None

        return decode_bonding_curve(raw_bytes)
    except Exception as exc:  # noqa: BLE001
        log.debug("Account %s nicht dekodierbar: %s", address, exc)
        return None
