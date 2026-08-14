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
    #: Absolute Untergrenze der Flip-Schwelle (fuer sehr kleine Kurven).
    net_sell_flip_threshold_sol: float = 0.05
    #: Eigentliche Schwelle: Anteil des ECHTEN SOL in der Kurve, der im
    #: Fenster abfliessen muss, damit es als Abverkauf gilt.
    #: Eine feste SOL-Schwelle taugt nicht - 0.05 SOL sind in einer 4-SOL-Kurve
    #: 1.3 %, in einer 11-SOL-Kurve 0.5 %. Beides ist blosses Rauschen.
    net_sell_flip_threshold_pct: float = 10.0

    #: So lange nach dem Einstieg loesen die "weichen" Ausstiege (Flip,
    #: Stillstand) nicht aus. Echte Notfaelle - Rug, Stop-Loss, leere Kurve,
    #: Migration - greifen weiterhin sofort.
    min_hold_before_soft_exit_sec: float = 15.0

    #: Wie weit ein Bonding-Curve-Account von der Standardbeziehung
    #: "virtuelles SOL - 30 == echtes SOL" abweichen darf, bevor der Token
    #: als nicht auswertbar gilt und gar nicht erst gehandelt wird.
    max_curve_layout_deviation_sol: float = 1.0

    #: Mindest-Deckung der Position durch echtes SOL in der Kurve.
    #: 1.0 = der Verkauf braechte genau das, was der Kurs verspricht.
    #: Normale Reibung (Gebuehr + Slippage) landet bei ca. 0.92.
    #: Faellt der Wert darunter, ist die Kurve leergezogen.
    min_liquidity_coverage: float = 0.6

    # --- Nachkaufen (Pyramiding) ---
    #: Wie oft darf derselbe Token gekauft werden? 1 = kein Nachkaufen.
    #: Nachkaeufe erhoehen das Risiko in EINEM Token - geht der hoch, gewinnst
    #: du mehr; ruggt er, verlierst du das Vielfache.
    max_entries_per_token: int = 2
    #: Nachgekauft wird nur, wenn die bestehende Position mindestens so weit
    #: im Plus steht. Verhindert das Verbilligen einer verlierenden Position -
    #: nachgelegt wird nur bei Staerke, nie bei Schwaeche.
    pyramid_min_gain_pct: float = 25.0

    # --- Stillstands-Ausstieg ---
    #: Passiert nach so vielen Sekunden nichts mehr, wird verkauft. Ersetzt
    #: den frueher sehr kurzen Zeitstopp: Laeufer duerfen laufen, aber totes
    #: Kapital blockiert keinen Platz mehr. 0 = aus.
    stagnation_after_sec: float = 90.0
    #: "Nichts passiert" heisst: Kurs bewegt sich in diesem Band um den
    #: Einstieg (in Prozent, plus wie minus).
    stagnation_band_pct: float = 15.0

    #: Obergrenze fuer das Momentum im Signalfenster. 0 = keine Obergrenze.
    #: Verhindert, dass der Bot die Spitze eines schon gelaufenen Spikes kauft.
    max_price_gain_in_window_pct: float = 0.0

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

    #: Windows waehrend des Betriebs am Einschlafen hindern. Ohne das haelt
    #: der Bot im Ruhezustand an - im Echtgeld-Modus mit offenen Positionen.
    prevent_sleep: bool = True

    # Dashboard
    dashboard_refresh_per_sec: int = 4
    dashboard_max_closed_rows: int = 8
    dashboard_max_log_rows: int = 6

    # Dateien
    trades_csv: str = "trades.csv"
    session_log: str = "session.log"


@dataclass(frozen=True)
class LiveConfig:
    """Einstellungen, die nur im Echtgeld-Modus greifen."""

    #: Not-Aus: bei diesem Verlust in Prozent des Startkapitals schaltet der
    #: Bot ab (offene Positionen werden vorher verkauft). 0 = aus.
    max_total_loss_pct: float = 30.0

    #: Slippage-Toleranz, die an PumpPortal uebergeben wird. Achtung: das ist
    #: NICHT `slippage_pct` aus der Simulation. Hier ist es die Obergrenze,
    #: ab der die Transaktion abgelehnt wird. Zu niedrig = viele
    #: fehlgeschlagene Snipes, zu hoch = schlechte Fills.
    order_slippage_pct: float = 15.0

    #: Priority Fee pro Transaktion in SOL. Hoeher = schneller im Block, aber
    #: teurer. Bei kleinen Positionen ist das der groesste Kostenblock.
    priority_fee_sol: float = 0.0005

    #: Wie lange auf die Blockchain-Bestaetigung eines Auftrags gewartet wird.
    fill_confirm_timeout_sec: float = 25.0
    fill_poll_interval_sec: float = 1.0

    #: Es wird nicht gekauft, wenn danach weniger als dieser Betrag auf der
    #: Wallet bliebe (Reserve fuer Transaktionsgebuehren).
    min_wallet_balance_sol: float = 0.02

    #: Countdown in Sekunden vor dem ersten echten Trade (Abbruch mit STRG+C).
    startup_countdown_sec: int = 8


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

    # ---- Betriebsart ----
    #: False = reine Simulation (Standard). True = ECHTES GELD.
    live_trading: bool = False
    live: LiveConfig = field(default_factory=LiveConfig)

    # ---- Laufzeitwerte (nicht aus der YAML) ----
    rpc_url: str = DEFAULT_RPC_URL
    #: PumpPortal-API-Key aus der .env - nur im Echtgeld-Modus noetig.
    pumpportal_api_key: str = ""
    #: Public Key der Bot-Wallet aus der .env - nur im Echtgeld-Modus noetig.
    bot_wallet_pubkey: str = ""
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
        net_sell_flip_threshold_pct=float(
            raw.get("net_sell_flip_threshold_pct", defaults.net_sell_flip_threshold_pct)),
        min_hold_before_soft_exit_sec=float(
            raw.get("min_hold_before_soft_exit_sec",
                    defaults.min_hold_before_soft_exit_sec)),
        max_price_gain_in_window_pct=float(
            raw.get("max_price_gain_in_window_pct",
                    defaults.max_price_gain_in_window_pct)),
        min_liquidity_coverage=float(
            raw.get("min_liquidity_coverage", defaults.min_liquidity_coverage)),
        max_curve_layout_deviation_sol=float(
            raw.get("max_curve_layout_deviation_sol",
                    defaults.max_curve_layout_deviation_sol)),
        max_entries_per_token=int(
            raw.get("max_entries_per_token", defaults.max_entries_per_token)),
        pyramid_min_gain_pct=float(
            raw.get("pyramid_min_gain_pct", defaults.pyramid_min_gain_pct)),
        stagnation_after_sec=float(
            raw.get("stagnation_after_sec", defaults.stagnation_after_sec)),
        stagnation_band_pct=float(
            raw.get("stagnation_band_pct", defaults.stagnation_band_pct)),
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
        prevent_sleep=bool(raw.get("prevent_sleep", defaults.prevent_sleep)),
        dashboard_refresh_per_sec=int(
            raw.get("dashboard_refresh_per_sec", defaults.dashboard_refresh_per_sec)),
        dashboard_max_closed_rows=int(
            raw.get("dashboard_max_closed_rows", defaults.dashboard_max_closed_rows)),
        dashboard_max_log_rows=int(
            raw.get("dashboard_max_log_rows", defaults.dashboard_max_log_rows)),
        trades_csv=str(raw.get("trades_csv", defaults.trades_csv)),
        session_log=str(raw.get("session_log", defaults.session_log)),
    )


def _build_live(raw: Any) -> LiveConfig:
    """Baut den `live:`-Block. Fehlt er, gelten die Defaults."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError("Der Block 'live:' in der config.yaml ist fehlerhaft.")

    defaults = LiveConfig()
    live = LiveConfig(
        max_total_loss_pct=float(
            raw.get("max_total_loss_pct", defaults.max_total_loss_pct)),
        order_slippage_pct=float(
            raw.get("order_slippage_pct", defaults.order_slippage_pct)),
        priority_fee_sol=float(
            raw.get("priority_fee_sol", defaults.priority_fee_sol)),
        fill_confirm_timeout_sec=float(
            raw.get("fill_confirm_timeout_sec", defaults.fill_confirm_timeout_sec)),
        fill_poll_interval_sec=float(
            raw.get("fill_poll_interval_sec", defaults.fill_poll_interval_sec)),
        min_wallet_balance_sol=float(
            raw.get("min_wallet_balance_sol", defaults.min_wallet_balance_sol)),
        startup_countdown_sec=int(
            raw.get("startup_countdown_sec", defaults.startup_countdown_sec)),
    )

    if not 0.0 <= live.max_total_loss_pct <= 100.0:
        raise ConfigError("live.max_total_loss_pct muss zwischen 0 und 100 liegen.")
    if not 0.0 < live.order_slippage_pct <= 100.0:
        raise ConfigError("live.order_slippage_pct muss zwischen 0 und 100 liegen.")
    if live.priority_fee_sol < 0:
        raise ConfigError("live.priority_fee_sol darf nicht negativ sein.")
    return live


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
        # Betriebsart: fehlt der Eintrag, wird bewusst simuliert.
        # Echtgeld muss man ausdruecklich einschalten, nie aus Versehen.
        live_trading=bool(data.get("live_trading", False)),
        live=_build_live(data.get("live")),
        # Laufzeit
        rpc_url=rpc_url,
        pumpportal_api_key=(os.getenv("PUMPPORTAL_API_KEY") or "").strip(),
        bot_wallet_pubkey=(os.getenv("BOT_WALLET_PUBKEY") or "").strip(),
        advanced=_build_advanced(data.get("advanced")),
    )

    _check_plausibility(cfg)
    _check_live_requirements(cfg)
    return cfg


def _check_live_requirements(cfg: Config) -> None:
    """
    Im Echtgeld-Modus muessen API-Key und Wallet-Adresse vorhanden sein.
    Lieber jetzt ein klarer Fehler als ein halb gestarteter Bot, der beim
    ersten Kauf abbricht.
    """
    if not cfg.live_trading:
        return

    if not cfg.pumpportal_api_key:
        raise ConfigError(
            "ECHTGELD-Modus ist eingeschaltet (live_trading: true), aber in der "
            ".env fehlt PUMPPORTAL_API_KEY.\n"
            "Den Key bekommst du auf https://pumpportal.fun/ unter "
            "'Lightning Transaction API', wenn du dort eine Wallet anlegst."
        )
    if not cfg.bot_wallet_pubkey:
        raise ConfigError(
            "ECHTGELD-Modus ist eingeschaltet (live_trading: true), aber in der "
            ".env fehlt BOT_WALLET_PUBKEY.\n"
            "Das ist die oeffentliche Adresse der Bot-Wallet - PumpPortal zeigt "
            "sie dir an, wenn du den API-Key erstellst. Sie ist nicht geheim; "
            "der Bot braucht sie nur, um Kontostaende zu pruefen."
        )
    # Grobe Plausibilitaet: Solana-Adressen sind Base58, 32-44 Zeichen.
    if not 32 <= len(cfg.bot_wallet_pubkey) <= 44:
        raise ConfigError(
            f"BOT_WALLET_PUBKEY sieht nicht wie eine Solana-Adresse aus "
            f"({len(cfg.bot_wallet_pubkey)} Zeichen, erwartet 32-44). "
            "Bitte die oeffentliche Adresse der Bot-Wallet eintragen - "
            "NICHT den API-Key und erst recht keinen Private Key."
        )


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
