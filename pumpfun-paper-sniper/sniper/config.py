"""
config.py -- laedt config.yaml und .env in ein typisiertes Objekt.

Warum ein eigenes Modul dafuer?
  * Alle Einstellungen liegen an einer Stelle und werden beim Start EINMAL
    geprueft. Tippfehler in der config.yaml fallen dann sofort auf, statt erst
    nach zehn Minuten Laufzeit mitten im Handel.
  * Der restliche Code arbeitet mit `cfg.take_profit_pct` statt mit
    `cfg["take_profit_pct"]` - das ist weniger fehleranfaellig.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Projektwurzel = der Ordner ueber "sniper/". Dort liegen config.yaml, .env,
# trades.csv und session.log.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_RPC_URL = "https://api.mainnet-beta.solana.com"


class ConfigError(RuntimeError):
    """Fehlerhafte oder unvollstaendige Konfiguration."""


@dataclass(frozen=True)
class AdvancedConfig:
    """Feineinstellungen aus dem `advanced:`-Block der config.yaml."""

    # Net-Sell-Flip
    net_sell_flip_window_sec: float = 5.0
    net_sell_flip_threshold_sol: float = 0.05

    # Curve
    initial_real_token_reserves: int = 793_100_000_000_000

    # Feed
    pumpportal_ws_url: str = "wss://pumpportal.fun/api/data"
    allowed_pools: tuple[str, ...] = ("pump",)
    ws_reconnect_min_sec: float = 1.0
    ws_reconnect_max_sec: float = 30.0

    # RPC
    rpc_timeout_sec: float = 10.0
    rpc_max_accounts_per_call: int = 100
    rpc_max_consecutive_errors: int = 50

    # Housekeeping
    candidate_max_lifetime_sec: float = 120.0

    # Dashboard
    dashboard_refresh_per_sec: int = 4
    dashboard_max_closed_rows: int = 8
    dashboard_max_log_rows: int = 6

    # Dateien
    trades_csv: str = "trades.csv"
    session_log: str = "session.log"


@dataclass(frozen=True)
class Config:
    """Alle Einstellungen des Bots (Hauptblock der config.yaml)."""

    # ---- Konto / Groesse ----
    start_balance_sol: float
    position_size_sol: float
    max_open_positions: int
    max_snipes_per_min: int

    # ---- Signalfenster ----
    signal_window_sec: float

    # ---- Einstiegs-Filter ----
    max_token_age_sec: float
    min_curve_progress_pct: float
    max_curve_progress_pct: float
    min_net_buy_volume_sol: float
    min_price_gain_in_window_pct: float
    max_dev_holding_pct: float
    skip_if_complete: bool

    # ---- Ausstieg ----
    hard_time_stop_sec: float
    take_profit_pct: float
    partial_take_profit_pct: float
    partial_take_profit_size: float
    stop_loss_pct: float
    trailing_activate_pct: float
    trailing_distance_pct: float
    rug_exit_drop_per_tick_pct: float
    exit_on_net_sell_flip: bool

    # ---- Ausfuehrungs-Simulation ----
    fee_pct: float
    slippage_pct: float
    simulated_priority_fee_sol: float
    rpc_poll_ms: int

    # ---- Laufzeitwerte (nicht aus der YAML) ----
    rpc_url: str = DEFAULT_RPC_URL
    advanced: AdvancedConfig = field(default_factory=AdvancedConfig)

    # -- abgeleitete Hilfswerte -------------------------------------------
    @property
    def rpc_poll_sec(self) -> float:
        """Poll-Intervall in Sekunden (die Config gibt Millisekunden an)."""
        return self.rpc_poll_ms / 1000.0

    @property
    def trades_csv_path(self) -> Path:
        return PROJECT_ROOT / self.advanced.trades_csv

    @property
    def session_log_path(self) -> Path:
        return PROJECT_ROOT / self.advanced.session_log


# ---------------------------------------------------------------------------
# Hilfsfunktionen zum Auslesen und Pruefen einzelner Werte
# ---------------------------------------------------------------------------
def _require(data: dict[str, Any], key: str) -> Any:
    """Holt einen Pflichtwert; wirft einen verstaendlichen Fehler, wenn er fehlt."""
    if key not in data:
        raise ConfigError(
            f"In der config.yaml fehlt der Eintrag '{key}'. "
            "Bitte die Zeile wieder einfuegen (Vorlage: config.yaml im Repo)."
        )
    return data[key]


def _as_float(data: dict[str, Any], key: str, *, minimum: float | None = None,
              maximum: float | None = None) -> float:
    raw = _require(data, key)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ConfigError(f"'{key}' muss eine Zahl sein, gefunden: {raw!r}") from None
    if minimum is not None and value < minimum:
        raise ConfigError(f"'{key}' muss >= {minimum} sein, gefunden: {value}")
    if maximum is not None and value > maximum:
        raise ConfigError(f"'{key}' muss <= {maximum} sein, gefunden: {value}")
    return value


def _as_int(data: dict[str, Any], key: str, *, minimum: int | None = None) -> int:
    raw = _require(data, key)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ConfigError(f"'{key}' muss eine ganze Zahl sein, gefunden: {raw!r}") from None
    if minimum is not None and value < minimum:
        raise ConfigError(f"'{key}' muss >= {minimum} sein, gefunden: {value}")
    return value


def _as_bool(data: dict[str, Any], key: str) -> bool:
    raw = _require(data, key)
    if isinstance(raw, bool):
        return raw
    raise ConfigError(f"'{key}' muss true oder false sein, gefunden: {raw!r}")


def _build_advanced(raw: Any) -> AdvancedConfig:
    """
    Baut den AdvancedConfig-Block. Fehlt der Block oder einzelne Werte darin,
    werden einfach die Defaults benutzt - der Bot laeuft also auch mit einer
    config.yaml ohne `advanced:`-Abschnitt.
    """
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError("Der Block 'advanced:' in der config.yaml ist fehlerhaft.")

    defaults = AdvancedConfig()
    pools = raw.get("allowed_pools", list(defaults.allowed_pools))
    if pools is None:
        pools = []
    if not isinstance(pools, list):
        raise ConfigError("'advanced.allowed_pools' muss eine Liste sein, z.B. [\"pump\"].")

    return AdvancedConfig(
        net_sell_flip_window_sec=float(
            raw.get("net_sell_flip_window_sec", defaults.net_sell_flip_window_sec)),
        net_sell_flip_threshold_sol=float(
            raw.get("net_sell_flip_threshold_sol", defaults.net_sell_flip_threshold_sol)),
        initial_real_token_reserves=int(
            raw.get("initial_real_token_reserves", defaults.initial_real_token_reserves)),
        pumpportal_ws_url=str(raw.get("pumpportal_ws_url", defaults.pumpportal_ws_url)),
        allowed_pools=tuple(str(p).lower() for p in pools),
        ws_reconnect_min_sec=float(
            raw.get("ws_reconnect_min_sec", defaults.ws_reconnect_min_sec)),
        ws_reconnect_max_sec=float(
            raw.get("ws_reconnect_max_sec", defaults.ws_reconnect_max_sec)),
        rpc_timeout_sec=float(raw.get("rpc_timeout_sec", defaults.rpc_timeout_sec)),
        rpc_max_accounts_per_call=int(
            raw.get("rpc_max_accounts_per_call", defaults.rpc_max_accounts_per_call)),
        rpc_max_consecutive_errors=int(
            raw.get("rpc_max_consecutive_errors", defaults.rpc_max_consecutive_errors)),
        candidate_max_lifetime_sec=float(
            raw.get("candidate_max_lifetime_sec", defaults.candidate_max_lifetime_sec)),
        dashboard_refresh_per_sec=int(
            raw.get("dashboard_refresh_per_sec", defaults.dashboard_refresh_per_sec)),
        dashboard_max_closed_rows=int(
            raw.get("dashboard_max_closed_rows", defaults.dashboard_max_closed_rows)),
        dashboard_max_log_rows=int(
            raw.get("dashboard_max_log_rows", defaults.dashboard_max_log_rows)),
        trades_csv=str(raw.get("trades_csv", defaults.trades_csv)),
        session_log=str(raw.get("session_log", defaults.session_log)),
    )


def load_config(config_path: Path | None = None,
                env_path: Path | None = None) -> Config:
    """
    Liest config.yaml + .env und gibt ein fertig geprueftes `Config`-Objekt zurueck.

    Reihenfolge:
      1. .env laden (setzt SOLANA_RPC_URL als Umgebungsvariable)
      2. config.yaml parsen
      3. jeden Wert pruefen (Typ + sinnvoller Bereich)
    """
    config_path = config_path or (PROJECT_ROOT / "config.yaml")
    env_path = env_path or (PROJECT_ROOT / ".env")

    # --- .env ---------------------------------------------------------------
    # override=False: eine bereits gesetzte Windows-Umgebungsvariable gewinnt.
    if env_path.exists():
        load_dotenv(env_path, override=False)

    rpc_url = (os.getenv("SOLANA_RPC_URL") or "").strip() or DEFAULT_RPC_URL
    if not rpc_url.startswith(("http://", "https://")):
        raise ConfigError(
            f"SOLANA_RPC_URL sieht nicht wie eine URL aus: {rpc_url!r}. "
            "Erwartet wird etwas wie https://api.mainnet-beta.solana.com"
        )

    # --- config.yaml --------------------------------------------------------
    if not config_path.exists():
        raise ConfigError(
            f"config.yaml wurde nicht gefunden ({config_path}). "
            "Sie muss im selben Ordner wie run.bat liegen."
        )
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(
            "config.yaml konnte nicht gelesen werden (YAML-Syntaxfehler).\n"
            "Haeufigste Ursache: ein Tabulator statt Leerzeichen.\n"
            f"Details: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ConfigError("config.yaml ist leer oder hat ein falsches Format.")

    cfg = Config(
        # Konto
        start_balance_sol=_as_float(data, "start_balance_sol", minimum=0.0001),
        position_size_sol=_as_float(data, "position_size_sol", minimum=0.0001),
        max_open_positions=_as_int(data, "max_open_positions", minimum=1),
        max_snipes_per_min=_as_int(data, "max_snipes_per_min", minimum=1),
        # Signalfenster
        signal_window_sec=_as_float(data, "signal_window_sec", minimum=0.0),
        # Einstieg
        max_token_age_sec=_as_float(data, "max_token_age_sec", minimum=0.0),
        min_curve_progress_pct=_as_float(data, "min_curve_progress_pct",
                                         minimum=0.0, maximum=100.0),
        max_curve_progress_pct=_as_float(data, "max_curve_progress_pct",
                                         minimum=0.0, maximum=100.0),
        min_net_buy_volume_sol=_as_float(data, "min_net_buy_volume_sol", minimum=0.0),
        min_price_gain_in_window_pct=_as_float(data, "min_price_gain_in_window_pct"),
        max_dev_holding_pct=_as_float(data, "max_dev_holding_pct",
                                      minimum=0.0, maximum=100.0),
        skip_if_complete=_as_bool(data, "skip_if_complete"),
        # Ausstieg
        hard_time_stop_sec=_as_float(data, "hard_time_stop_sec", minimum=1.0),
        take_profit_pct=_as_float(data, "take_profit_pct", minimum=0.0),
        partial_take_profit_pct=_as_float(data, "partial_take_profit_pct", minimum=0.0),
        partial_take_profit_size=_as_float(data, "partial_take_profit_size",
                                           minimum=0.0, maximum=1.0),
        stop_loss_pct=_as_float(data, "stop_loss_pct", minimum=0.0, maximum=100.0),
        trailing_activate_pct=_as_float(data, "trailing_activate_pct", minimum=0.0),
        trailing_distance_pct=_as_float(data, "trailing_distance_pct",
                                        minimum=0.0, maximum=100.0),
        rug_exit_drop_per_tick_pct=_as_float(data, "rug_exit_drop_per_tick_pct",
                                             minimum=0.0, maximum=100.0),
        exit_on_net_sell_flip=_as_bool(data, "exit_on_net_sell_flip"),
        # Ausfuehrung
        fee_pct=_as_float(data, "fee_pct", minimum=0.0, maximum=50.0),
        slippage_pct=_as_float(data, "slippage_pct", minimum=0.0, maximum=90.0),
        simulated_priority_fee_sol=_as_float(data, "simulated_priority_fee_sol",
                                             minimum=0.0),
        rpc_poll_ms=_as_int(data, "rpc_poll_ms", minimum=100),
        # Laufzeit
        rpc_url=rpc_url,
        advanced=_build_advanced(data.get("advanced")),
    )

    _check_plausibility(cfg)
    return cfg


def _check_plausibility(cfg: Config) -> None:
    """
    Prueft Kombinationen von Werten, die einzeln in Ordnung sind, zusammen aber
    keinen Sinn ergeben. Besser jetzt ein klarer Fehler als spaeter komisches
    Verhalten im Handel.
    """
    if cfg.min_curve_progress_pct > cfg.max_curve_progress_pct:
        raise ConfigError(
            "min_curve_progress_pct darf nicht groesser sein als "
            f"max_curve_progress_pct ({cfg.min_curve_progress_pct} > "
            f"{cfg.max_curve_progress_pct})."
        )
    if cfg.position_size_sol > cfg.start_balance_sol:
        raise ConfigError(
            "position_size_sol ist groesser als das Startguthaben - so kaeme nie "
            "ein Trade zustande."
        )
    if cfg.partial_take_profit_pct >= cfg.take_profit_pct:
        raise ConfigError(
            "partial_take_profit_pct muss kleiner sein als take_profit_pct, "
            "sonst wird der Teilverkauf nie ausgeloest."
        )
    if cfg.signal_window_sec >= cfg.max_token_age_sec:
        raise ConfigError(
            "signal_window_sec muss kleiner sein als max_token_age_sec, sonst "
            "ist jeder Token nach dem Beobachtungsfenster schon 'zu alt'."
        )
    if cfg.max_open_positions * cfg.position_size_sol > cfg.start_balance_sol:
        # Kein harter Fehler - nur ein Hinweis im Log (wird spaeter geloggt).
        pass
