"""
Tests fuer strategy.py -- Einstiegsfilter und Ausstiegs-Prioritaeten.

Besonders wichtig ist die Reihenfolge der Ausstiegsregeln:
    Migriert -> Rug -> Stop-Loss -> (Teil-)Take-Profit -> Trailing
             -> Net-Sell-Flip -> Hard-Time-Stop
"""

from __future__ import annotations

import time

import pytest

from sniper.feed import NewTokenEvent
from sniper.paper_engine import ExitReason, Position
from sniper.strategy import (
    FlowTracker,
    decide_exit,
    evaluate_entry,
    make_candidate,
)

from .test_curve import INITIAL_VIRTUAL_SOL, INITIAL_VIRTUAL_TOKEN, build_account
from .test_paper_engine import curve_at, make_config

from sniper.curve import decode_bonding_curve


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------
def make_event(**overrides) -> NewTokenEvent:
    """Ein Launch-Event, wie es der Feed liefert (Dev haelt 3 % des Angebots)."""
    base = dict(
        mint="MintA",
        symbol="AAA",
        name="Token A",
        creator="DevWallet",
        bonding_curve="CurveA",
        initial_buy_tokens=30_000_000.0,   # 3 % von 1 Mrd
        initial_buy_sol=1.0,
        v_tokens=INITIAL_VIRTUAL_TOKEN / 1e6,
        v_sol=INITIAL_VIRTUAL_SOL / 1e9,
        market_cap_sol=30.0,
        pool="pump",
        received_at=time.monotonic(),
    )
    base.update(overrides)
    return NewTokenEvent(**base)


def make_candidate_with(*, sol_in_curve: float, gain_source_sol: float,
                        age_sec: float = 10.5, **event_overrides):
    """
    Baut einen Kandidaten fuer die Einstiegspruefung.

    `sol_in_curve`     = wie viel SOL beim Launch-Event schon in der Kurve war
                         (das ist der Startpunkt des Beobachtungsfensters)
    `gain_source_sol`  = wie viel SOL waehrend des Fensters dazukommt
                         (das ist genau der gemessene Kaufdruck)
    """
    start_state = curve_at(sol_in_curve)

    # Das Feed-Event muss zum Startzustand passen - daraus leitet der Bot den
    # Startpreis und die Basis fuer den Kaufdruck ab.
    defaults = dict(
        v_sol=start_state.virtual_sol_reserves / 1e9,
        v_tokens=start_state.virtual_token_reserves / 1e6,
        received_at=time.monotonic() - age_sec,
    )
    defaults.update(event_overrides)
    event = make_event(**defaults)
    candidate = make_candidate(event)

    now = time.monotonic()
    # Erster Messpunkt: Zustand direkt nach dem Launch
    candidate.on_tick(start_state, now - 1.0)
    # Zweiter Messpunkt: nach dem Zufluss im Fenster
    candidate.on_tick(curve_at(sol_in_curve + gain_source_sol), now)
    return candidate


def make_position(entry_price: float, last_price: float, *,
                  age_sec: float = 5.0, peak_price: float | None = None,
                  partial_done: bool = False) -> Position:
    position = Position(
        mint="MintA", symbol="AAA", name="", bonding_curve="CurveA",
        tokens=1_000_000.0, tokens_initial=1_000_000.0,
        entry_price=entry_price, sol_spent=0.15,
        last_price=last_price,
        peak_price=peak_price if peak_price is not None else max(entry_price, last_price),
        partial_done=partial_done,
    )
    position.opened_at = time.monotonic() - age_sec
    return position


# ---------------------------------------------------------------------------
# Einstieg
# ---------------------------------------------------------------------------
def test_guter_kandidat_wird_gekauft(tmp_path):
    cfg = make_config(tmp_path)
    # 5 SOL sind schon drin (Progress > 1 %), im Fenster kommen 3 SOL dazu.
    candidate = make_candidate_with(sol_in_curve=5.0, gain_source_sol=3.0)

    decision = evaluate_entry(candidate, cfg)

    assert decision.buy is True, decision.reason


def test_skip_wenn_kaufdruck_zu_klein(tmp_path):
    cfg = make_config(tmp_path)
    candidate = make_candidate_with(sol_in_curve=5.0, gain_source_sol=0.3)

    decision = evaluate_entry(candidate, cfg)

    assert decision.buy is False
    assert "Kaufdruck" in decision.reason


def test_skip_wenn_momentum_zu_schwach(tmp_path):
    """
    Kaufdruck reicht (2 SOL), aber die Kurve ist schon so voll, dass 2 SOL den
    Preis kaum noch bewegen -> das Momentum-Kriterium greift.
    """
    cfg = make_config(tmp_path, min_net_buy_volume_sol=1.5,
                      min_price_gain_in_window_pct=30.0)
    candidate = make_candidate_with(sol_in_curve=5.0, gain_source_sol=2.0)

    decision = evaluate_entry(candidate, cfg)

    assert decision.buy is False
    assert "Momentum" in decision.reason


def test_skip_wenn_dev_zu_viel_haelt(tmp_path):
    cfg = make_config(tmp_path)
    candidate = make_candidate_with(
        sol_in_curve=5.0, gain_source_sol=3.0,
        initial_buy_tokens=250_000_000.0,  # 25 % des Angebots
    )

    decision = evaluate_entry(candidate, cfg)

    assert decision.buy is False
    assert "Dev" in decision.reason


def test_skip_wenn_token_zu_alt(tmp_path):
    cfg = make_config(tmp_path)
    candidate = make_candidate_with(sol_in_curve=5.0, gain_source_sol=3.0, age_sec=90.0)

    decision = evaluate_entry(candidate, cfg)

    assert decision.buy is False
    assert "zu alt" in decision.reason


def test_skip_wenn_progress_zu_hoch(tmp_path):
    """Kurve schon weit gelaufen (viel SOL drin) -> zu spaet zum Snipen."""
    cfg = make_config(tmp_path)
    candidate = make_candidate_with(sol_in_curve=55.0, gain_source_sol=5.0)

    decision = evaluate_entry(candidate, cfg)

    assert decision.buy is False
    assert "Progress zu hoch" in decision.reason


def test_skip_wenn_progress_zu_niedrig(tmp_path):
    """Frische Kurve ohne jeden Kauf -> Progress 0 %, wird uebersprungen."""
    cfg = make_config(tmp_path, min_net_buy_volume_sol=0.0,
                      min_price_gain_in_window_pct=0.0)
    candidate = make_candidate_with(sol_in_curve=0.0, gain_source_sol=0.0)

    decision = evaluate_entry(candidate, cfg)

    assert decision.buy is False
    assert "Progress zu niedrig" in decision.reason


def test_skip_wenn_migriert(tmp_path):
    cfg = make_config(tmp_path)
    candidate = make_candidate_with(sol_in_curve=5.0, gain_source_sol=3.0)
    candidate.last_state = decode_bonding_curve(build_account(complete=True))

    decision = evaluate_entry(candidate, cfg)

    assert decision.buy is False
    assert "migriert" in decision.reason


def test_skip_ohne_kursdaten(tmp_path):
    cfg = make_config(tmp_path)
    candidate = make_candidate(make_event())

    decision = evaluate_entry(candidate, cfg)

    assert decision.buy is False
    assert "RPC" in decision.reason


def test_skip_bei_nur_einem_messpunkt(tmp_path):
    """Mit einem einzigen Messpunkt gibt es keine Veraenderung zu messen."""
    cfg = make_config(tmp_path)
    candidate = make_candidate(make_event())
    candidate.on_tick(curve_at(5.0), time.monotonic())

    decision = evaluate_entry(candidate, cfg)

    assert decision.buy is False
    assert "Messpunkte" in decision.reason


def test_skip_wenn_der_abverkauf_schon_laeuft(tmp_path):
    """
    Nachstellung eines Trades aus dem echten Betrieb (TISM6900):

        SNIPE ... Progress 34.9% | Kaufdruck 7.46 SOL | Momentum +50.4%
        Exit  ... (FLIP): -2.83 SOL Nettoabfluss in 5s     <- eine Sekunde spaeter

    Ueber das ganze Fenster war der Kaufdruck klar positiv, aber in den
    letzten Sekunden lief der Abverkauf bereits. Der Bot kaufte die Spitze und
    warf sie sofort wieder weg - zweimal Gebuehren fuer nichts.

    Es darf keine Position eroeffnet werden, die die Ausstiegslogik im
    naechsten Tick sofort wieder schliessen wuerde.
    """
    cfg = make_config(tmp_path)
    event = make_event(received_at=time.monotonic() - 10.5)
    candidate = make_candidate(event)

    now = time.monotonic()
    # Erst laeuft der Kurs stark hoch (Kaufdruck und Momentum sind top) ...
    candidate.on_tick(curve_at(4.0), now - 9.0)
    candidate.on_tick(curve_at(9.0), now - 6.0)
    candidate.on_tick(curve_at(12.0), now - 4.0)
    # ... dann kippt es in den letzten Sekunden.
    candidate.on_tick(curve_at(10.5), now - 1.0)
    candidate.on_tick(curve_at(9.5), now)

    # Die klassischen Filter wuerden alle passen:
    assert candidate.net_buy_volume_sol > cfg.min_net_buy_volume_sol
    assert candidate.price_gain_pct > cfg.min_price_gain_in_window_pct

    # Trotzdem darf nicht gekauft werden.
    decision = evaluate_entry(candidate, cfg)
    assert decision.buy is False
    assert "Abverkauf" in decision.reason


def test_kauf_erlaubt_wenn_der_kaufdruck_noch_anhaelt(tmp_path):
    """Gegenprobe: steigt der Kurs bis zuletzt, wird gekauft."""
    cfg = make_config(tmp_path)
    event = make_event(received_at=time.monotonic() - 10.5)
    candidate = make_candidate(event)

    now = time.monotonic()
    candidate.on_tick(curve_at(4.0), now - 9.0)
    candidate.on_tick(curve_at(6.0), now - 6.0)
    candidate.on_tick(curve_at(7.5), now - 3.0)
    candidate.on_tick(curve_at(8.5), now)

    decision = evaluate_entry(candidate, cfg)
    assert decision.buy is True, decision.reason


def test_momentum_obergrenze_optional(tmp_path):
    """
    max_price_gain_in_window_pct ist standardmaessig aus. Wird sie gesetzt,
    werden zu weit gelaufene Token uebersprungen.
    """
    cfg = make_config(tmp_path)
    candidate = make_candidate_with(sol_in_curve=4.0, gain_source_sol=6.0)

    # Ohne Obergrenze: Kauf
    assert evaluate_entry(candidate, cfg).buy is True

    # Mit enger Obergrenze: Skip
    object.__setattr__(cfg.advanced, "max_price_gain_in_window_pct", 10.0)
    decision = evaluate_entry(candidate, cfg)
    assert decision.buy is False
    assert "zu weit gelaufen" in decision.reason


# ---------------------------------------------------------------------------
# Regressionstest zu einem Fehler aus dem echten Betrieb
# ---------------------------------------------------------------------------
def test_kaufdruck_ignoriert_die_werte_aus_dem_feed_event(tmp_path):
    """
    Kaufdruck und Momentum muessen ausschliesslich aus Kettendaten stammen.

    Hintergrund: Zuerst kam der Startwert aus dem Feed-Event
    (`vSolInBondingCurve`), alle weiteren Werte von der Blockchain. Was
    PumpPortal in dem Feld liefert, deckt sich aber nicht mit dem
    `virtual_sol_reserves` des Bonding-Curve-Accounts - die Differenz war
    damit wertlos. Im Betrieb meldete der Bot dadurch "13,10 SOL Kaufdruck"
    bei einer Kurve, in der laut Curve-Progress nur ~1,3 SOL stecken konnten,
    und kaufte massenhaft Schrott.

    Dieser Test setzt das Event bewusst auf voellig andere Werte als die Kette.
    Gemessen werden darf nur die Bewegung auf der Kette.
    """
    cfg = make_config(tmp_path)

    # Das Event behauptet Unsinn (18 SOL in der Kurve, ganz anderer Preis).
    event = make_event(
        v_sol=18.0,
        v_tokens=500_000_000.0,
        received_at=time.monotonic() - 10.5,
    )
    candidate = make_candidate(event)

    # Die Kette sagt: 5.0 SOL drin, dann kommen 0.4 SOL dazu.
    now = time.monotonic()
    candidate.on_tick(curve_at(5.0), now - 1.0)
    candidate.on_tick(curve_at(5.4), now)

    # Kaufdruck = genau die 0.4 SOL von der Kette, nicht die Differenz
    # zum erfundenen Event-Wert (die waere ~17 SOL gewesen).
    assert candidate.net_buy_volume_sol == pytest.approx(0.4, abs=0.01)

    # Momentum ebenso: gerechnet von Kettenpreis zu Kettenpreis.
    erwartet = (curve_at(5.4).price_sol / curve_at(5.0).price_sol - 1.0) * 100.0
    assert candidate.price_gain_pct == pytest.approx(erwartet, rel=1e-9)

    # Und in der Gesamtentscheidung schlaegt sich das nieder: 0.4 SOL
    # Kaufdruck reicht nicht (Mindestwert 1.5).
    decision = evaluate_entry(candidate, cfg)
    assert decision.buy is False
    assert "Kaufdruck" in decision.reason


def test_kaufdruck_und_progress_passen_zusammen(tmp_path):
    """
    Plausibilitaetsprobe: Der gemessene Kaufdruck darf nie groesser sein als
    das SOL, das laut Curve-Progress ueberhaupt in der Kurve stecken kann.
    Genau diese Bedingung war im Fehlerfall verletzt.
    """
    candidate = make_candidate(make_event())
    now = time.monotonic()
    candidate.on_tick(curve_at(0.0), now - 1.0)   # frische Kurve
    candidate.on_tick(curve_at(3.0), now)         # 3 SOL sind zugeflossen

    state = candidate.last_state
    assert state is not None

    kaufdruck = candidate.net_buy_volume_sol
    sol_in_der_kurve = state.real_sol          # was tatsaechlich drin liegt

    assert kaufdruck == pytest.approx(3.0, abs=0.01)
    assert kaufdruck <= sol_in_der_kurve + 0.01


# ---------------------------------------------------------------------------
# Ausstieg
# ---------------------------------------------------------------------------
def test_liquiditaets_notausgang(tmp_path):
    """
    Regressionstest zu 9 Trades aus dem echten Betrieb (u.a. ECLIPS, FC, CURWAR):
    Der Kurs stand nahezu still (-4.5 %, bei FC sogar +5.2 %), die Position war
    aber zu 100 % wertlos - die Kurve war leergezogen. Der Stop-Loss schaut nur
    auf den Kurs und griff deshalb nie; die Trades liefen bis zum Zeitstopp.
    Zusammen 38 % des Gesamtverlusts.

    Nachgestellt mit einer Kurve, deren virtuelle Reserven einen normalen Kurs
    ergeben, in der aber praktisch kein echtes SOL mehr liegt.
    """
    cfg = make_config(tmp_path)

    gesund = curve_at(10.0)
    leergezogen = decode_bonding_curve(build_account(
        v_sol=gesund.virtual_sol_reserves,      # Kurs sieht unveraendert aus
        v_tok=gesund.virtual_token_reserves,
        r_tok=gesund.real_token_reserves,
        r_sol=1_000_000,                        # 0.001 SOL - praktisch leer
    ))

    # Der Kurs ist derselbe - daran wuerde man nichts merken.
    assert leergezogen.price_sol == pytest.approx(gesund.price_sol)

    position = make_position(entry_price=gesund.price_sol,
                             last_price=gesund.price_sol)

    # Gesunde Kurve: halten.
    assert decide_exit(position, gesund, cfg, tick_drop_pct=0.0,
                       net_flow_sol=0.0).action == "hold"

    # Leergezogene Kurve: sofort raus, obwohl der Kurs unveraendert ist.
    decision = decide_exit(position, leergezogen, cfg,
                           tick_drop_pct=0.0, net_flow_sol=0.0)
    assert decision.action == "close"
    assert decision.reason == ExitReason.LIQUIDITY
    assert "Kurve leer" in decision.detail


def test_normale_reibung_loest_den_notausgang_nicht_aus(tmp_path):
    """
    Gegenprobe: Gebuehr und Slippage druecken die Deckung immer auf ~0.92.
    Das darf den Notausgang nicht ausloesen, sonst wuerde er staendig feuern.
    """
    cfg = make_config(tmp_path)
    state = curve_at(10.0)
    position = make_position(entry_price=state.price_sol, last_price=state.price_sol)

    decision = decide_exit(position, state, cfg, tick_drop_pct=0.0, net_flow_sol=0.0)

    assert decision.action == "hold"


def test_rug_hat_vorrang_vor_allem(tmp_path):
    """
    Kurs steht +30 % (also im Bereich des Teil-Take-Profits), ist aber gerade
    um 25 % in einem Tick eingebrochen -> Rug-Exit muss gewinnen.
    """
    cfg = make_config(tmp_path)
    position = make_position(entry_price=1.0, last_price=1.3)

    decision = decide_exit(position, curve_at(10.0), cfg,
                           tick_drop_pct=25.0, net_flow_sol=0.0)

    assert decision.action == "close"
    assert decision.reason == ExitReason.RUG


def test_stop_loss_vor_take_profit(tmp_path):
    cfg = make_config(tmp_path)
    position = make_position(entry_price=1.0, last_price=0.7)  # -30 %

    decision = decide_exit(position, curve_at(10.0), cfg,
                           tick_drop_pct=0.0, net_flow_sol=0.0)

    assert decision.action == "close"
    assert decision.reason == ExitReason.STOP_LOSS


def test_voller_take_profit(tmp_path):
    cfg = make_config(tmp_path)
    position = make_position(entry_price=1.0, last_price=1.45)  # +45 %

    decision = decide_exit(position, curve_at(10.0), cfg,
                           tick_drop_pct=0.0, net_flow_sol=0.0)

    assert decision.action == "close"
    assert decision.reason == ExitReason.TAKE_PROFIT


def test_teil_take_profit_bei_25_prozent(tmp_path):
    cfg = make_config(tmp_path)
    position = make_position(entry_price=1.0, last_price=1.28)  # +28 %

    decision = decide_exit(position, curve_at(10.0), cfg,
                           tick_drop_pct=0.0, net_flow_sol=0.0)

    assert decision.action == "partial"
    assert decision.reason == ExitReason.PARTIAL_TP
    assert decision.fraction == pytest.approx(0.5)


def test_teil_take_profit_nur_einmal(tmp_path):
    cfg = make_config(tmp_path)
    position = make_position(entry_price=1.0, last_price=1.28, partial_done=True)

    decision = decide_exit(position, curve_at(10.0), cfg,
                           tick_drop_pct=0.0, net_flow_sol=0.0)

    # Trailing ist ab +20 % aktiv, der Kurs steht aber auf dem Hoch -> halten
    assert decision.action == "hold"


def test_trailing_stop_greift_nach_aktivierung(tmp_path):
    cfg = make_config(tmp_path)
    # Der Kurs stand bei +35 % - dabei wird das Trailing scharfgeschaltet.
    position = make_position(entry_price=1.0, last_price=1.35, partial_done=True)
    decision = decide_exit(position, curve_at(10.0), cfg,
                           tick_drop_pct=0.0, net_flow_sol=0.0)
    assert decision.action == "hold"
    assert position.trailing_active is True

    # Rueckgang auf +15 % -> 14.8 % unter dem Hoch, knapp unter dem Limit
    position.last_price = 1.15
    decision = decide_exit(position, curve_at(10.0), cfg,
                           tick_drop_pct=0.0, net_flow_sol=0.0)
    assert decision.action == "hold"

    # Weiter runter auf +10 % -> 18.5 % unter dem Hoch, Trailing loest aus
    position.last_price = 1.10
    decision = decide_exit(position, curve_at(10.0), cfg,
                           tick_drop_pct=0.0, net_flow_sol=0.0)

    assert decision.action == "close"
    assert decision.reason == ExitReason.TRAILING


def test_trailing_erst_nach_aktivierungsschwelle(tmp_path):
    """
    Der Kurs war nie ueber +20 %, also ist das Trailing nicht scharf - ein
    Rueckgang vom Hoch darf hier noch nicht ausloesen.
    """
    cfg = make_config(tmp_path)
    position = make_position(entry_price=1.0, last_price=1.02, peak_price=1.18)

    decision = decide_exit(position, curve_at(10.0), cfg,
                           tick_drop_pct=0.0, net_flow_sol=0.0)

    assert decision.action == "hold"
    assert position.trailing_active is False


def test_net_sell_flip_loest_aus(tmp_path):
    cfg = make_config(tmp_path)
    position = make_position(entry_price=1.0, last_price=1.05)

    decision = decide_exit(position, curve_at(10.0), cfg,
                           tick_drop_pct=0.0, net_flow_sol=-0.4)

    assert decision.action == "close"
    assert decision.reason == ExitReason.NET_SELL_FLIP


def test_kleiner_abfluss_loest_noch_nicht_aus(tmp_path):
    """Unterhalb der Schwelle (0.05 SOL) gilt es als Rauschen, nicht als Flip."""
    cfg = make_config(tmp_path)
    position = make_position(entry_price=1.0, last_price=1.05)

    decision = decide_exit(position, curve_at(10.0), cfg,
                           tick_drop_pct=0.0, net_flow_sol=-0.01)

    assert decision.action == "hold"


def test_net_sell_flip_abschaltbar(tmp_path):
    cfg = make_config(tmp_path, exit_on_net_sell_flip=False)
    position = make_position(entry_price=1.0, last_price=1.05)

    decision = decide_exit(position, curve_at(10.0), cfg,
                           tick_drop_pct=0.0, net_flow_sol=-5.0)

    assert decision.action == "hold"


def test_harter_zeitstopp_greift_immer(tmp_path):
    """
    Kein anderer Grund trifft zu (Kurs seitwaerts, kein Abfluss) - nach
    hard_time_stop_sec wird trotzdem verkauft.
    """
    cfg = make_config(tmp_path)
    position = make_position(entry_price=1.0, last_price=1.02, age_sec=121.0)

    decision = decide_exit(position, curve_at(10.0), cfg,
                           tick_drop_pct=0.0, net_flow_sol=0.0)

    assert decision.action == "close"
    assert decision.reason == ExitReason.TIME_STOP


def test_migrierter_token_wird_sofort_geschlossen(tmp_path):
    cfg = make_config(tmp_path)
    position = make_position(entry_price=1.0, last_price=1.5)
    migriert = decode_bonding_curve(build_account(complete=True))

    decision = decide_exit(position, migriert, cfg,
                           tick_drop_pct=0.0, net_flow_sol=0.0)

    assert decision.action == "close"
    assert decision.reason == ExitReason.MIGRATED


def test_ohne_kursdaten_wird_gehalten_aber_zeitstopp_zaehlt(tmp_path):
    cfg = make_config(tmp_path)

    # RPC-Aussetzer, Position noch jung -> halten
    jung = make_position(entry_price=1.0, last_price=1.0, age_sec=5.0)
    assert decide_exit(jung, None, cfg, tick_drop_pct=0.0,
                       net_flow_sol=0.0).action == "hold"

    # RPC-Aussetzer, Position ueber dem Zeitstopp -> trotzdem raus
    alt = make_position(entry_price=1.0, last_price=1.0, age_sec=200.0)
    decision = decide_exit(alt, None, cfg, tick_drop_pct=0.0, net_flow_sol=0.0)
    assert decision.action == "close"
    assert decision.reason == ExitReason.TIME_STOP


def test_position_wird_nie_laenger_als_der_zeitstopp_gehalten(tmp_path):
    """
    Absicherung gegen den wichtigsten Wunsch: keine langen Holds.
    Egal welcher Kurs anliegt - nach hard_time_stop_sec ist Schluss.
    """
    cfg = make_config(tmp_path)
    for kurs in (0.99, 1.0, 1.05, 1.19):  # alles unterhalb aller anderen Trigger
        position = make_position(entry_price=1.0, last_price=kurs, age_sec=121.0)
        decision = decide_exit(position, curve_at(10.0), cfg,
                               tick_drop_pct=0.0, net_flow_sol=0.0)
        assert decision.action == "close", f"Kurs {kurs} wurde nicht geschlossen"


# ---------------------------------------------------------------------------
# FlowTracker
# ---------------------------------------------------------------------------
def test_flowtracker_misst_zufluss_und_abfluss():
    tracker = FlowTracker()
    now = 1000.0
    tracker.add(now - 10.0, 30_000_000_000)   # 30 SOL
    tracker.add(now - 3.0, 32_000_000_000)    # 32 SOL
    tracker.add(now, 31_500_000_000)          # 31.5 SOL

    # Ueber die letzten 5 Sekunden: von 32 auf 31.5 -> -0.5 SOL
    assert tracker.net_flow_sol(5.0, now) == pytest.approx(-0.5)
    # Ueber die letzten 20 Sekunden: von 30 auf 31.5 -> +1.5 SOL
    assert tracker.net_flow_sol(20.0, now) == pytest.approx(1.5)


def test_flowtracker_ohne_daten_gibt_null():
    tracker = FlowTracker()
    assert tracker.net_flow_sol(5.0, 1000.0) == 0.0
    tracker.add(1000.0, 30_000_000_000)
    assert tracker.net_flow_sol(5.0, 1000.0) == 0.0
