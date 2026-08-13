"""
Tests fuer curve.py -- Dekodierung und Fill-Simulation.

Ausfuehren:  python -m pytest -q
"""

from __future__ import annotations

import struct

import pytest

from sniper.curve import (
    BONDING_CURVE_DISCRIMINATOR,
    DEFAULT_INITIAL_REAL_TOKEN_RESERVES,
    CurveDecodeError,
    CurveState,
    decode_bonding_curve,
    simulate_buy,
    simulate_sell,
)

# Startwerte einer frischen pump.fun-Kurve (aus dem Global-Account).
INITIAL_VIRTUAL_TOKEN = 1_073_000_000_000_000   # 1.073 Mrd Token (6 Decimals)
INITIAL_VIRTUAL_SOL = 30_000_000_000            # 30 SOL in Lamports
INITIAL_REAL_TOKEN = 793_100_000_000_000


def build_account(
    *,
    v_tok: int = INITIAL_VIRTUAL_TOKEN,
    v_sol: int = INITIAL_VIRTUAL_SOL,
    r_tok: int = INITIAL_REAL_TOKEN,
    r_sol: int = 0,
    supply: int = 1_000_000_000_000_000,
    complete: bool = False,
    with_creator: bool = True,
) -> bytes:
    """Baut die Rohbytes eines Bonding-Curve-Accounts, wie sie on-chain stehen."""
    data = bytearray(BONDING_CURVE_DISCRIMINATOR)
    data += struct.pack("<Q", v_tok)
    data += struct.pack("<Q", v_sol)
    data += struct.pack("<Q", r_tok)
    data += struct.pack("<Q", r_sol)
    data += struct.pack("<Q", supply)
    data += bytes([1 if complete else 0])
    if with_creator:
        data += bytes(32)  # Creator-Pubkey (Inhalt hier egal)
    return bytes(data)


# ---------------------------------------------------------------------------
# Dekodierung
# ---------------------------------------------------------------------------
def test_decode_liest_alle_felder():
    state = decode_bonding_curve(build_account(r_sol=5_000_000_000))

    assert state.virtual_token_reserves == INITIAL_VIRTUAL_TOKEN
    assert state.virtual_sol_reserves == INITIAL_VIRTUAL_SOL
    assert state.real_token_reserves == INITIAL_REAL_TOKEN
    assert state.real_sol_reserves == 5_000_000_000
    assert state.token_total_supply == 1_000_000_000_000_000
    assert state.complete is False
    assert state.creator is not None and len(state.creator) == 32


def test_decode_ohne_creator_feld_funktioniert():
    """Aeltere Accounts haben das Creator-Feld nicht - das darf nicht crashen."""
    state = decode_bonding_curve(build_account(with_creator=False))
    assert state.creator is None
    assert state.virtual_sol_reserves == INITIAL_VIRTUAL_SOL


def test_decode_lehnt_fremden_account_ab():
    fremd = bytes(8) + bytes(48)
    with pytest.raises(CurveDecodeError):
        decode_bonding_curve(fremd)


def test_decode_lehnt_zu_kurze_daten_ab():
    with pytest.raises(CurveDecodeError):
        decode_bonding_curve(BONDING_CURVE_DISCRIMINATOR + bytes(8))


# ---------------------------------------------------------------------------
# Preis und Progress
# ---------------------------------------------------------------------------
def test_startpreis_entspricht_der_formel():
    state = decode_bonding_curve(build_account())
    erwartet = (INITIAL_VIRTUAL_SOL / 1e9) / (INITIAL_VIRTUAL_TOKEN / 1e6)
    assert state.price_sol == pytest.approx(erwartet, rel=1e-12)
    # Sanity: ~2.8e-8 SOL pro Token beim Launch
    assert 1e-8 < state.price_sol < 1e-7


def test_progress_von_null_bis_hundert():
    frisch = decode_bonding_curve(build_account(r_tok=INITIAL_REAL_TOKEN))
    assert frisch.progress_pct(DEFAULT_INITIAL_REAL_TOKEN_RESERVES) == pytest.approx(0.0)

    halb = decode_bonding_curve(build_account(r_tok=INITIAL_REAL_TOKEN // 2))
    assert halb.progress_pct(DEFAULT_INITIAL_REAL_TOKEN_RESERVES) == pytest.approx(
        50.0, abs=0.01)

    leer = decode_bonding_curve(build_account(r_tok=0))
    assert leer.progress_pct(DEFAULT_INITIAL_REAL_TOKEN_RESERVES) == pytest.approx(100.0)


def test_migrierter_token_ist_nicht_handelbar():
    state = decode_bonding_curve(build_account(complete=True))
    assert state.is_tradable is False
    assert state.progress_pct() == 100.0


def test_leere_kurve_ist_nicht_handelbar():
    state = decode_bonding_curve(build_account(v_tok=0))
    assert state.is_tradable is False
    assert state.price_sol == 0.0


# ---------------------------------------------------------------------------
# Kauf-Simulation
# ---------------------------------------------------------------------------
def test_kauf_zieht_gebuehr_ab_und_liefert_token():
    state = decode_bonding_curve(build_account())
    quote = simulate_buy(state, 1.0, fee_pct=1.0, slippage_pct=0.0)

    assert quote.fee_sol == pytest.approx(0.01)
    assert quote.sol_after_fee == pytest.approx(0.99)
    assert quote.tokens_out > 0
    # Effektiver Einstiegspreis liegt ueber dem Spotpreis (Gebuehr + Kurveneffekt)
    assert quote.avg_price_sol > quote.spot_price_before


def test_kauf_ohne_gebuehr_folgt_der_constant_product_formel():
    state = decode_bonding_curve(build_account())
    sol_in = 2.0
    quote = simulate_buy(state, sol_in, fee_pct=0.0, slippage_pct=0.0)

    lamports = sol_in * 1e9
    erwartet_raw = (INITIAL_VIRTUAL_TOKEN * lamports) / (INITIAL_VIRTUAL_SOL + lamports)
    assert quote.tokens_out == pytest.approx(erwartet_raw / 1e6, rel=1e-9)


def test_slippage_verringert_die_tokenmenge():
    state = decode_bonding_curve(build_account())
    ohne = simulate_buy(state, 1.0, fee_pct=1.0, slippage_pct=0.0)
    mit = simulate_buy(state, 1.0, fee_pct=1.0, slippage_pct=3.0)

    assert mit.tokens_out == pytest.approx(ohne.tokens_out * 0.97, rel=1e-9)
    assert mit.avg_price_sol > ohne.avg_price_sol


def test_grosser_kauf_ist_teurer_pro_token():
    """Preisauswirkung: wer mehr kauft, zahlt im Schnitt mehr (Slippage der Kurve)."""
    state = decode_bonding_curve(build_account())
    klein = simulate_buy(state, 0.1, fee_pct=1.0, slippage_pct=0.0)
    gross = simulate_buy(state, 10.0, fee_pct=1.0, slippage_pct=0.0)
    assert gross.avg_price_sol > klein.avg_price_sol


def test_kauf_auf_migrierter_kurve_wird_abgelehnt():
    state = decode_bonding_curve(build_account(complete=True))
    with pytest.raises(ValueError):
        simulate_buy(state, 1.0, fee_pct=1.0, slippage_pct=0.0)


# ---------------------------------------------------------------------------
# Verkauf-Simulation
# ---------------------------------------------------------------------------
def test_verkauf_liefert_weniger_als_der_kauf_gekostet_hat():
    """
    Sofort-Rueckverkauf ohne Kursbewegung muss ein Minus ergeben -
    zweimal Gebuehr plus zweimal Slippage. Sonst waere die Simulation
    unrealistisch guenstig.
    """
    state = decode_bonding_curve(build_account(r_sol=100_000_000_000))
    # 0.15 SOL entspricht der Standard-Positionsgroesse aus der config.yaml.
    kauf = simulate_buy(state, 0.15, fee_pct=1.0, slippage_pct=3.0)
    verkauf = simulate_sell(state, kauf.tokens_out, fee_pct=1.0, slippage_pct=3.0)

    assert verkauf.sol_out < kauf.sol_in
    # Grobe Erwartung: ~8 % Reibungsverlust (2x1% Gebuehr, 2x3% Slippage)
    # plus etwas Kurveneffekt.
    verlust_pct = (1 - verkauf.sol_out / kauf.sol_in) * 100
    assert 6.0 < verlust_pct < 12.0


def test_grosser_trade_verliert_mehr_durch_preisauswirkung():
    """
    Je groesser der Trade im Verhaeltnis zur Kurve, desto mehr frisst die
    Preisauswirkung. 1 SOL in eine 30-SOL-Kurve kostet deutlich mehr als
    0.15 SOL - genau das soll die Simulation abbilden.
    """
    state = decode_bonding_curve(build_account(r_sol=100_000_000_000))

    def rundlauf_verlust_pct(sol_in: float) -> float:
        kauf = simulate_buy(state, sol_in, fee_pct=1.0, slippage_pct=3.0)
        verkauf = simulate_sell(state, kauf.tokens_out, fee_pct=1.0, slippage_pct=3.0)
        return (1 - verkauf.sol_out / kauf.sol_in) * 100

    assert rundlauf_verlust_pct(1.0) > rundlauf_verlust_pct(0.15)


def test_verkauf_ist_durch_reales_sol_gedeckelt():
    """
    In der Kurve kann nie mehr SOL ausgezahlt werden, als real drin liegt -
    auch wenn die virtuellen Reserven rechnerisch mehr hergeben wuerden.
    """
    state = decode_bonding_curve(build_account(r_sol=1_000_000_000))  # 1 SOL real
    verkauf = simulate_sell(state, 500_000_000, fee_pct=0.0, slippage_pct=0.0)
    assert verkauf.sol_gross <= 1.0
    assert verkauf.sol_out <= 1.0


def test_verkauf_auf_toter_kurve_ergibt_null():
    state = CurveState(0, 0, 0, 0, 0, True)
    verkauf = simulate_sell(state, 1000.0, fee_pct=1.0, slippage_pct=3.0)
    assert verkauf.sol_out == 0.0


def test_verkauf_von_null_token_ist_ein_fehler():
    state = decode_bonding_curve(build_account())
    with pytest.raises(ValueError):
        simulate_sell(state, 0.0, fee_pct=1.0, slippage_pct=3.0)


def test_kurssteigerung_macht_den_verkauf_profitabel():
    """
    Kauf auf frischer Kurve, danach kaufen andere nach (SOL-Reserve steigt) ->
    der Verkauf muss mehr einbringen als der Einsatz.
    """
    start = decode_bonding_curve(build_account())
    kauf = simulate_buy(start, 0.15, fee_pct=1.0, slippage_pct=3.0)

    # 20 SOL Kaufdruck von anderen: Preis steigt deutlich.
    spaeter = decode_bonding_curve(build_account(
        v_sol=INITIAL_VIRTUAL_SOL + 20_000_000_000,
        v_tok=int(INITIAL_VIRTUAL_TOKEN * INITIAL_VIRTUAL_SOL
                  / (INITIAL_VIRTUAL_SOL + 20_000_000_000)),
        r_sol=20_000_000_000,
    ))
    verkauf = simulate_sell(spaeter, kauf.tokens_out, fee_pct=1.0, slippage_pct=3.0)

    assert verkauf.sol_out > kauf.sol_in
    assert spaeter.price_sol > start.price_sol
