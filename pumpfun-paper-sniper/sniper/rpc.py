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
import time
from dataclasses import dataclass

import httpx

from .config import Config
from .curve import CurveState, decode_bonding_curve
from .safety import assert_read_only_rpc_method

log = logging.getLogger(__name__)

#: Standard-Token-Programm von Solana - zum Auflisten aller Token einer Wallet.
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"


@dataclass(frozen=True)
class TxEffect:
    """
    Was eine einzelne Transaktion mit der Bot-Wallet gemacht hat.

    sol_delta   negativ = SOL ist abgeflossen (Kauf), positiv = zugeflossen
                (Verkauf). Netzwerk- und Priority-Fees sind bereits enthalten.
    token_delta positiv = Token erhalten, negativ = Token abgegeben.
    success     False, wenn die Transaktion on-chain fehlgeschlagen ist.
                Achtung: eine fehlgeschlagene Transaktion kostet trotzdem
                Gebuehren - `sol_delta` ist dann leicht negativ.
    """

    success: bool
    sol_delta: float
    token_delta: float


def _parse_tx_effect(result: dict, wallet: str, mint: str | None) -> TxEffect:
    """Zerlegt die Antwort von getTransaction in einen `TxEffect`."""
    meta = result.get("meta") or {}
    success = meta.get("err") is None

    # --- SOL-Veraenderung der Bot-Wallet ---
    message = (result.get("transaction") or {}).get("message") or {}
    keys: list[str] = []
    for entry in message.get("accountKeys") or []:
        keys.append(entry.get("pubkey", "") if isinstance(entry, dict) else str(entry))

    sol_delta = 0.0
    index = keys.index(wallet) if wallet in keys else 0
    pre = meta.get("preBalances") or []
    post = meta.get("postBalances") or []
    if index < len(pre) and index < len(post):
        sol_delta = (int(post[index]) - int(pre[index])) / 1_000_000_000

    # --- Token-Veraenderung ---
    token_delta = 0.0
    if mint:
        def summe(entries: list | None) -> float:
            total = 0.0
            for entry in entries or []:
                if entry.get("mint") != mint:
                    continue
                # `owner` fehlt in aelteren RPC-Antworten - dann zaehlen wir
                # den Eintrag mit, weil die Wallet der einzige Besitzer ist,
                # dessen Konten hier auftauchen koennen.
                owner = entry.get("owner")
                if owner not in (None, wallet):
                    continue
                amount = (entry.get("uiTokenAmount") or {}).get("uiAmount")
                total += float(amount or 0.0)
            return total

        token_delta = summe(meta.get("postTokenBalances")) \
            - summe(meta.get("preTokenBalances"))

    return TxEffect(success=success, sol_delta=sol_delta, token_delta=token_delta)


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
        # Kann bewusst None sein - z.B. bei getTransaction, solange die
        # Transaktion noch nicht bestaetigt ist.
        return data.get("result")

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

            accounts = (raw or {}).get("value") or []
            for address, account in zip(chunk, accounts):
                result[address] = _decode_account(address, account)

        return result


    # -- Kontostaende der Bot-Wallet (nur im Echtgeld-Modus gebraucht) -----
    async def get_sol_balance(self, pubkey: str) -> float | None:
        """
        SOL-Guthaben einer Wallet. Gibt None zurueck, wenn die Abfrage
        fehlschlaegt - der Aufrufer entscheidet dann, was zu tun ist.

        Wird gebraucht, um nach einem Trade den tatsaechlichen Geldfluss zu
        messen (Differenz vorher/nachher) und um den Not-Aus zu pruefen.
        """
        try:
            result = await self._call("getBalance", [pubkey, {"commitment": "confirmed"}])
            lamports = (result or {}).get("value")
            if lamports is None:
                return None
            return int(lamports) / 1_000_000_000
        except Exception as exc:  # noqa: BLE001
            log.warning("SOL-Kontostand nicht abrufbar: %s", exc)
            return None

    async def get_token_balance(self, owner: str, mint: str) -> float | None:
        """
        Wie viele Token eines bestimmten Mints liegen in der Wallet?

        Damit prueft der Bot, ob ein Kauf oder Verkauf wirklich angekommen ist
        ("Fill-Bestaetigung"). Auf die Antwort der Handels-API allein kann man
        sich nicht verlassen: eine Transaktion kann trotz "gesendet" auf der
        Blockchain scheitern. Der Kontostand ist die Wahrheit.

        Gibt 0.0 zurueck, wenn es (noch) kein Token-Konto gibt, und None, wenn
        die Abfrage selbst fehlgeschlagen ist - das ist ein wichtiger
        Unterschied: 0 heisst "nichts da", None heisst "weiss ich nicht".
        """
        try:
            result = await self._call("getTokenAccountsByOwner", [
                owner,
                {"mint": mint},
                {"encoding": "jsonParsed", "commitment": "confirmed"},
            ])
        except Exception as exc:  # noqa: BLE001
            log.warning("Token-Kontostand nicht abrufbar: %s", exc)
            return None

        total = 0.0
        for entry in (result or {}).get("value") or []:
            try:
                info = entry["account"]["data"]["parsed"]["info"]["tokenAmount"]
                total += float(info.get("uiAmount") or 0.0)
            except (KeyError, TypeError, ValueError):
                continue
        return total

    async def list_token_holdings(self, owner: str) -> dict[str, float] | None:
        """
        Listet ALLE Token auf, die in der Wallet liegen (Mint -> Menge).

        Wird vom Notverkauf-Skript gebraucht, um Reste einzusammeln, die der
        Bot nicht mehr losgeworden ist. Gibt None zurueck, wenn die Abfrage
        fehlschlaegt.
        """
        try:
            result = await self._call("getTokenAccountsByOwner", [
                owner,
                {"programId": TOKEN_PROGRAM_ID},
                {"encoding": "jsonParsed", "commitment": "confirmed"},
            ])
        except Exception as exc:  # noqa: BLE001
            log.warning("Token-Bestaende nicht abrufbar: %s", exc)
            return None

        holdings: dict[str, float] = {}
        for entry in (result or {}).get("value") or []:
            try:
                info = entry["account"]["data"]["parsed"]["info"]
                amount = float(info["tokenAmount"].get("uiAmount") or 0.0)
                if amount > 0:
                    holdings[info["mint"]] = holdings.get(info["mint"], 0.0) + amount
            except (KeyError, TypeError, ValueError):
                continue
        return holdings

    async def get_transaction_effect(
        self, signature: str, wallet: str, mint: str | None = None, *,
        timeout_sec: float = 25.0, poll_interval_sec: float = 1.0,
    ) -> "TxEffect | None":
        """
        Schlaegt eine bereits gesendete Transaktion nach und liest daraus den
        EXAKTEN Geldfluss dieser einen Transaktion.

        Warum das noetig ist: Man koennte den SOL-Aufwand auch aus der
        Differenz des Wallet-Kontostands vorher/nachher berechnen. Das ist
        aber falsch, sobald mehrere Auftraege gleichzeitig laufen - dann
        mischt sich der Erloes eines Verkaufs in die Messung eines Kaufs, und
        die Zahlen werden Unsinn. Die Transaktion selbst kennt dagegen nur
        ihre eigenen Buchungen.

        Nebenbei liefert sie die einzige verlaessliche Antwort auf die Frage
        "hat es geklappt?": `meta.err`.

        Gibt None zurueck, wenn die Transaktion nicht innerhalb der Zeit
        auffindbar war (dann faellt der Aufrufer auf Kontostaende zurueck).
        """
        deadline = time.monotonic() + timeout_sec

        while time.monotonic() < deadline:
            try:
                result = await self._call("getTransaction", [
                    signature,
                    {"encoding": "jsonParsed", "commitment": "confirmed",
                     "maxSupportedTransactionVersion": 0},
                ])
            except Exception as exc:  # noqa: BLE001
                log.debug("getTransaction fehlgeschlagen: %s", exc)
                result = None

            if result:
                return _parse_tx_effect(result, wallet, mint)

            await asyncio.sleep(poll_interval_sec)

        log.warning("Transaktion %s war nach %.0fs noch nicht auffindbar.",
                    signature[:16], timeout_sec)
        return None


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
