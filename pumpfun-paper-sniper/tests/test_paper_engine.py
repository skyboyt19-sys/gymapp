"""
Tests fuer paper_engine.py -- Buchhaltung des virtuellen Kontos.

Die wichtigste Eigenschaft: das Guthaben muss am Ende exakt der Summe aus
Startguthaben und allen Trade-Ergebnissen entsprechen. Wenn das stimmt, ist
die Simulation in sich schluessig.
"""

from __future__ import annotations

import pytest

from sniper.config import AdvancedConfig, Config
from sniper.curve import decode_bonding_curve
from sniper.paper_engine import ExitReason, PaperEngine

from .test_curve import (
    INITIAL_REAL_TOKEN,
    INITIAL_VIRTUAL_SOL,
    INITIAL_VIRTUAL_TOKEN,
    build_account,
)


def make_config(tmp_path, **overrides) -> Config:
    """Basiskonfiguration fuer die Tests (entspricht der ausgelieferten config.yaml)."""
    base = dict(
        start_balance_sol=10.0,
        position_size_sol=0.15,
        max_open_positions=4,
        max_snipes_per_min=8,
        signal_window_sec=10.0,
        max_token_age_sec=45.0,
        min_curve_progress_pct=1.0,
        max_curve_progress_pct=40.0,
        min_net_buy_volume_sol=1.5,
        min_price_gain_in_window_pct=8.0,
        max_dev_holding_pct=10.0,
        skip_if_complete=True,
        hard_time_stop_sec=120.0,
        take_profit_pct=40.0,
        partial_take_profit_pct=25.0,
        partial_take_profit_size=0.5,
        stop_loss_pct=25.0,
        trailing_activate_pct=20.0,
        trailing_distance_pct=15.0,
        rug_exit_drop_per_tick_pct=20.0,
        exit_on_net_sell_flip=True,
        fee_pct=1.0,
        slippage_pct=3.0,
        simulated_priority_fee_sol=0.0005,
        rpc_poll_ms=800,
        rpc_url="https://example.invalid",
        advanced=AdvancedConfig(
            trades_csv=str(tmp_path / "trades.csv"),
            session_log=str(tmp_path / "session.log"),
        ),
    )
    base.update(overrides)
    return Config(**base)


def curve_at(sol_added: float = 0.0):
    """
    Bonding-Curve-Zustand, nachdem `sol_added` SOL in die Kurve geflossen sind.

    Die virtuellen Reserven folgen der Constant-Product-Formel, und die reale
    Token-Reserve sinkt um genau die Menge, die dabei aus der Kurve geht -
    dadurch ergibt sich auch ein realistischer Curve-Progress.
    """
    added = int(sol_added * 1e9)
    v_sol = INITIAL_VIRTUAL_SOL + added
    v_tok = int(INITIAL_VIRTUAL_TOKEN * INITIAL_VIRTUAL_SOL / v_sol)
    verkaufte_token = INITIAL_VIRTUAL_TOKEN - v_tok
    r_tok = max(0, INITIAL_REAL_TOKEN - verkaufte_token)
    return decode_bonding_curve(
        build_account(v_sol=v_sol, v_tok=v_tok, r_tok=r_tok, r_sol=added))


# ---------------------------------------------------------------------------
def test_kauf_bucht_guthaben_korrekt_ab(tmp_path):
    cfg = make_config(tmp_path)
    engine = PaperEngine(cfg)
    state = curve_at(5.0)

    position = engine.open_position(
        mint="MintA", symbol="AAA", name="Token A",
        bonding_curve="CurveA", state=state,
    )

    assert position is not None
    erwartete_kosten = cfg.position_size_sol + cfg.simulated_priority_fee_sol
    assert engine.balance_sol == pytest.approx(cfg.start_balance_sol - erwartete_kosten)
    assert position.sol_spent == pytest.approx(erwartete_kosten)
    assert position.tokens > 0
    assert engine.tokens_sniped == 1
    # Effektiver Einstiegspreis = alles Bezahlte geteilt durch erhaltene Token
    assert position.entry_price == pytest.approx(
        erwartete_kosten / position.tokens, rel=1e-12)


def test_kein_doppelkauf_desselben_tokens(tmp_path):
    engine = PaperEngine(make_config(tmp_path))
    state = curve_at(5.0)
    args = dict(mint="MintA", symbol="AAA", name="A", bonding_curve="CurveA", state=state)

    assert engine.open_position(**args) is not None
    assert engine.open_position(**args) is None
    assert len(engine.positions) == 1


def test_limit_offener_positionen(tmp_path):
    cfg = make_config(tmp_path, max_open_positions=2)
    engine = PaperEngine(cfg)
    state = curve_at(5.0)

    for i in range(4):
        engine.open_position(
            mint=f"Mint{i}", symbol=f"T{i}", name="", bonding_curve=f"C{i}", state=state)

    assert len(engine.positions) == 2


def test_limit_snipes_pro_minute(tmp_path):
    cfg = make_config(tmp_path, max_snipes_per_min=2, max_open_positions=10)
    engine = PaperEngine(cfg)
    state = curve_at(5.0)

    for i in range(5):
        engine.open_position(
            mint=f"Mint{i}", symbol=f"T{i}", name="", bonding_curve=f"C{i}", state=state)

    assert engine.tokens_sniped == 2


def test_kauf_bei_zu_kleinem_guthaben_wird_abgelehnt(tmp_path):
    cfg = make_config(tmp_path, start_balance_sol=0.1, position_size_sol=0.05,
                      max_open_positions=10, max_snipes_per_min=100)
    engine = PaperEngine(cfg)
    state = curve_at(5.0)

    for i in range(10):
        engine.open_position(
            mint=f"Mint{i}", symbol=f"T{i}", name="", bonding_curve=f"C{i}", state=state)

    assert engine.balance_sol >= 0.0
    assert engine.tokens_sniped == 1  # danach reicht das Guthaben nicht mehr


# ---------------------------------------------------------------------------
def test_sofortiger_rueckverkauf_ergibt_verlust(tmp_path):
    """Ohne Kursbewegung frisst die Reibung (Gebuehr + Slippage) den Trade auf."""
    cfg = make_config(tmp_path)
    engine = PaperEngine(cfg)
    state = curve_at(5.0)

    position = engine.open_position(
        mint="MintA", symbol="AAA", name="", bonding_curve="CurveA", state=state)
    assert position is not None

    trade = engine.close_position(position, state, ExitReason.TIME_STOP)

    assert trade.pnl_sol < 0
    assert trade.exit_reason == "TIME"
    assert engine.positions == {}
    assert len(engine.closed_trades) == 1


def test_kurssteigerung_ergibt_gewinn(tmp_path):
    cfg = make_config(tmp_path)
    engine = PaperEngine(cfg)

    position = engine.open_position(
        mint="MintA", symbol="AAA", name="", bonding_curve="CurveA", state=curve_at(5.0))
    assert position is not None

    # Andere kaufen fuer 30 SOL nach -> Kurs steigt deutlich
    trade = engine.close_position(position, curve_at(35.0), ExitReason.TAKE_PROFIT)

    assert trade.pnl_sol > 0
    assert trade.pnl_pct > 0
    assert engine.win_rate_pct == 100.0


def test_guthaben_stimmt_mit_der_trade_summe_ueberein(tmp_path):
    """
    Die zentrale Konsistenzpruefung: Endguthaben = Startguthaben + Summe aller
    Trade-Ergebnisse. Wenn das nicht stimmt, ist irgendwo SOL "verschwunden".
    """
    cfg = make_config(tmp_path)
    engine = PaperEngine(cfg)

    for i, sol_danach in enumerate([35.0, 2.0, 12.0]):
        position = engine.open_position(
            mint=f"Mint{i}", symbol=f"T{i}", name="",
            bonding_curve=f"C{i}", state=curve_at(5.0))
        assert position is not None
        engine.close_position(position, curve_at(sol_danach), ExitReason.TIME_STOP)

    assert engine.balance_sol == pytest.approx(
        cfg.start_balance_sol + engine.realized_pnl_sol, rel=1e-9)


def test_teilverkauf_haelt_die_position_offen(tmp_path):
    cfg = make_config(tmp_path)
    engine = PaperEngine(cfg)

    position = engine.open_position(
        mint="MintA", symbol="AAA", name="", bonding_curve="CurveA", state=curve_at(5.0))
    assert position is not None
    tokens_vorher = position.tokens

    erloes = engine.partial_sell(position, curve_at(20.0), 0.5, ExitReason.PARTIAL_TP)

    assert erloes > 0
    assert position.partial_done is True
    assert position.tokens == pytest.approx(tokens_vorher * 0.5)
    assert "MintA" in engine.positions          # bleibt offen
    assert position.sol_received == pytest.approx(erloes)


def test_teilverkauf_dann_totalverlust_ist_besser_als_kein_teilverkauf(tmp_path):
    """
    Der Sinn des Teil-Take-Profits: selbst wenn der Rest wertlos wird, ist der
    Trade dank des Teilverkaufs weniger schlimm.
    """
    cfg = make_config(tmp_path)
    engine = PaperEngine(cfg)

    position = engine.open_position(
        mint="MintA", symbol="AAA", name="", bonding_curve="CurveA", state=curve_at(5.0))
    assert position is not None
    # +18 % Kurs: der Teilverkauf bringt Geld, deckt aber nicht den Einsatz.
    engine.partial_sell(position, curve_at(8.0), 0.5, ExitReason.PARTIAL_TP)

    # Danach zieht der Dev die Liquiditaet: der Rest ist praktisch wertlos.
    trade = engine.close_position(position, curve_at(0.0001), ExitReason.RUG)

    assert trade.had_partial is True
    # Verlust kleiner als der volle Einsatz, weil der Teilverkauf Geld brachte
    assert -cfg.position_size_sol < trade.pnl_sol < 0


def test_schliessen_ohne_kursdaten_bewertet_zum_letzten_kurs(tmp_path):
    """
    Faellt die RPC beim Schliessen aus, wird der Restbestand zum zuletzt
    gesehenen Kurs bewertet - abzueglich Gebuehr und Slippage. Das ist die
    beste verfuegbare Schaetzung; 0 anzusetzen waere willkuerlich zu pessimistisch.
    """
    cfg = make_config(tmp_path)
    engine = PaperEngine(cfg)

    position = engine.open_position(
        mint="MintA", symbol="AAA", name="", bonding_curve="CurveA", state=curve_at(5.0))
    assert position is not None
    # Kurs hat sich verdoppelt, dann faellt die RPC aus.
    engine.update_position_price(position, position.entry_price * 2.0)

    trade = engine.close_position(position, None, ExitReason.SHUTDOWN)

    erwartet = (position.tokens_initial * position.entry_price * 2.0
                * (1 - cfg.slippage_pct / 100) * (1 - cfg.fee_pct / 100)
                - cfg.simulated_priority_fee_sol)
    assert trade.sol_received == pytest.approx(erwartet)
    assert trade.pnl_sol > 0
    assert engine.balance_sol == pytest.approx(
        cfg.start_balance_sol - position.sol_spent + erwartet)


def test_ohne_je_gesehenen_kurs_ist_der_rest_wertlos(tmp_path):
    """Kein einziger Kurs bekannt (last_price = 0) -> Restbestand = 0 SOL."""
    cfg = make_config(tmp_path)
    engine = PaperEngine(cfg)

    position = engine.open_position(
        mint="MintA", symbol="AAA", name="", bonding_curve="CurveA", state=curve_at(5.0))
    assert position is not None
    position.last_price = 0.0

    trade = engine.close_position(position, None, ExitReason.SHUTDOWN)

    assert trade.sol_received == 0.0
    assert trade.pnl_sol == pytest.approx(-position.sol_spent)


def test_migrierter_token_wird_nicht_als_totalverlust_gebucht(tmp_path):
    """
    Migration zu PumpSwap ist der Erfolgsfall eines Tokens: die Kurve ist voll
    und der Kurs am Hoch. Der Bot handelt dort nicht weiter, darf die Position
    aber auch nicht mit 0 bewerten.
    """
    from sniper.curve import decode_bonding_curve
    from .test_curve import build_account

    cfg = make_config(tmp_path)
    engine = PaperEngine(cfg)

    position = engine.open_position(
        mint="MintA", symbol="AAA", name="", bonding_curve="CurveA", state=curve_at(5.0))
    assert position is not None
    # Kurs lief bis zur Migration deutlich hoch.
    engine.update_position_price(position, position.entry_price * 3.0)

    trade = engine.close_position(
        position, decode_bonding_curve(build_account(complete=True)),
        ExitReason.MIGRATED)

    assert trade.pnl_sol > 0
    assert trade.sol_received > 0


# ---------------------------------------------------------------------------
def test_trades_csv_wird_geschrieben(tmp_path):
    cfg = make_config(tmp_path)
    engine = PaperEngine(cfg)

    position = engine.open_position(
        mint="MintA", symbol="AAA", name="", bonding_curve="CurveA", state=curve_at(5.0))
    assert position is not None
    engine.close_position(position, curve_at(20.0), ExitReason.TAKE_PROFIT)

    zeilen = cfg.trades_csv_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(zeilen) == 3                      # Kopfzeile + OPEN + CLOSE
    assert zeilen[0].startswith("zeit_utc;")
    assert ";OPEN;" in zeilen[1]
    assert ";CLOSE;" in zeilen[2]
    assert "AAA" in zeilen[2]


def test_trefferquote_und_zusammenfassung(tmp_path):
    cfg = make_config(tmp_path)
    engine = PaperEngine(cfg)

    # Ein Gewinner, ein Verlierer
    for i, sol_danach in enumerate([40.0, 5.0]):
        position = engine.open_position(
            mint=f"Mint{i}", symbol=f"T{i}", name="",
            bonding_curve=f"C{i}", state=curve_at(5.0))
        assert position is not None
        engine.close_position(position, curve_at(sol_danach), ExitReason.TIME_STOP)

    assert engine.win_rate_pct == pytest.approx(50.0)
    text = "\n".join(engine.summary_lines())
    assert "Endguthaben" in text
    assert "Trefferquote" in text
