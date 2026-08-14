"""
Tests fuer live_engine.py -- der Echtgeld-Modus.

Hier wird natuerlich NICHT wirklich gehandelt: PumpPortal und die Solana-RPC
sind durch Attrappen ersetzt, die sich wie das echte System verhalten
(inklusive Fehlerfaellen).

Geprueft wird vor allem das, was im Ernstfall Geld kostet:
  * Wird der tatsaechliche Fill gebucht - nicht der erhoffte?
  * Was passiert, wenn ein Auftrag scheitert?
  * Greift der Not-Aus?
  * Kann derselbe Verkauf versehentlich doppelt rausgehen?
"""

from __future__ import annotations

import asyncio

import pytest

from sniper.live_engine import LiveEngine
from sniper.paper_engine import ExitReason
from sniper.pumpportal_trade import TradeResult
from sniper.rpc import TxEffect

from .test_paper_engine import curve_at, make_config


# ---------------------------------------------------------------------------
# Attrappen
# ---------------------------------------------------------------------------
class FakeTrader:
    """Tut so, als waere sie die PumpPortal-Lightning-API."""

    def __init__(self, *, buy_ok: bool = True, sell_ok: bool = True) -> None:
        self.buy_ok = buy_ok
        self.sell_ok = sell_ok
        self.slippage_pct = 15.0
        self.priority_fee_sol = 0.0005
        self.buys: list[tuple[str, float]] = []
        self.sells: list[tuple[str, float]] = []

    async def buy(self, mint: str, sol_amount: float) -> TradeResult:
        self.buys.append((mint, sol_amount))
        if self.buy_ok:
            return TradeResult(True, signature="SIG_BUY")
        return TradeResult(False, error="Slippage zu hoch")

    async def sell_percent(self, mint: str, percent: float) -> TradeResult:
        self.sells.append((mint, percent))
        if self.sell_ok:
            return TradeResult(True, signature="SIG_SELL")
        return TradeResult(False, error="Transaktion fehlgeschlagen")


class FakeRpc:
    """
    Tut so, als waere sie die Solana-RPC.

    `sol_balance` / `token_balance` sind die Kontostaende, `effects` bildet
    das Nachschlagen einzelner Transaktionen ab (Signatur -> TxEffect).
    Ist zu einer Signatur nichts hinterlegt, verhaelt sich die Attrappe wie
    eine RPC, die die Transaktion (noch) nicht kennt.
    """

    def __init__(self, sol: float = 1.0) -> None:
        self.sol_balance = sol
        self.token_balance = 0.0
        self.sol_reads = 0
        self.effects: dict[str, TxEffect] = {}

    async def get_sol_balance(self, pubkey: str) -> float | None:
        self.sol_reads += 1
        return self.sol_balance

    async def get_token_balance(self, owner: str, mint: str) -> float | None:
        return self.token_balance

    async def get_transaction_effect(self, signature: str, wallet: str,
                                     mint: str | None = None, **_kw) -> TxEffect | None:
        return self.effects.get(signature)


def make_engine(tmp_path, *, trader=None, rpc=None, start_sol: float = 1.0,
                **cfg_overrides) -> LiveEngine:
    cfg = make_config(tmp_path, **cfg_overrides)
    # Wartezeiten im Test auf ein Minimum: sonst dauert jeder Test 25 Sekunden.
    object.__setattr__(cfg.live, "fill_confirm_timeout_sec", 0.3)
    object.__setattr__(cfg.live, "fill_poll_interval_sec", 0.01)
    return LiveEngine(
        cfg,
        trader or FakeTrader(),
        rpc or FakeRpc(start_sol),
        "BotWalletPubkey11111111111111111111111111",
        start_sol,
    )


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Kauf
# ---------------------------------------------------------------------------
def test_kauf_bucht_den_tatsaechlichen_fill(tmp_path):
    """
    Entscheidend: gebucht wird, was wirklich ankam - Tokenmenge aus dem
    Wallet-Bestand, ausgegebenes SOL aus der Transaktion selbst. Nicht das,
    was bestellt wurde.
    """
    rpc = FakeRpc(sol=1.0)
    trader = FakeTrader()
    engine = make_engine(tmp_path, trader=trader, rpc=rpc, start_sol=1.0)
    # Die Transaktion hat 0.1525 SOL gekostet und 1.234.567 Token gebracht.
    rpc.effects["SIG_BUY"] = TxEffect(success=True, sol_delta=-0.1525,
                                      token_delta=1_234_567.0)

    async def szenario():
        async def nach_dem_kauf():
            await asyncio.sleep(0.02)
            rpc.sol_balance = 0.8475
            rpc.token_balance = 1_234_567.0

        asyncio.create_task(nach_dem_kauf())
        await engine._do_open("MintA", "AAA", "Token A", "CurveA", curve_at(5.0))

    run(szenario())

    assert trader.buys == [("MintA", 0.15)]
    position = engine.positions["MintA"]
    assert position.tokens == pytest.approx(1_234_567.0)
    assert position.sol_spent == pytest.approx(0.1525)
    assert position.entry_price == pytest.approx(position.sol_spent / position.tokens)
    assert engine.balance_sol == pytest.approx(1.0 - 0.1525)
    assert engine.tokens_sniped == 1


def test_paralleler_auftrag_verfaelscht_die_buchung_nicht(tmp_path):
    """
    Der wichtigste Test dieses Moduls.

    Waehrend der Kauf laeuft, wird ein Verkauf einer anderen Position
    bestaetigt und schiebt SOL auf die Wallet. Wuerde der Bot den Aufwand aus
    der Differenz des Kontostands berechnen, kaeme hier ein viel zu kleiner
    (oder negativer) Wert heraus - und damit ein voellig falsches P&L.
    Weil er stattdessen die Transaktion selbst liest, stimmt die Buchung.
    """
    rpc = FakeRpc(sol=1.0)
    trader = FakeTrader()
    engine = make_engine(tmp_path, trader=trader, rpc=rpc, start_sol=1.0)
    rpc.effects["SIG_BUY"] = TxEffect(success=True, sol_delta=-0.1525,
                                      token_delta=1_000_000.0)

    async def szenario():
        async def stoerung():
            await asyncio.sleep(0.02)
            rpc.token_balance = 1_000_000.0
            # Ein fremder Verkauf bringt gleichzeitig 0.9 SOL herein:
            # der Kontostand STEIGT waehrend des Kaufs.
            rpc.sol_balance = 1.7475

        asyncio.create_task(stoerung())
        await engine._do_open("MintA", "AAA", "Token A", "CurveA", curve_at(5.0))

    run(szenario())

    position = engine.positions["MintA"]
    assert position.sol_spent == pytest.approx(0.1525)   # nicht 0, nicht negativ
    assert position.entry_price > 0


def test_fehlgeschlagener_kauf_legt_keine_position_an(tmp_path):
    """Auftrag abgelehnt und keine Token angekommen -> keine Position, kein Geld gebunden."""
    rpc = FakeRpc(sol=1.0)          # Token-Bestand bleibt 0
    trader = FakeTrader(buy_ok=False)
    engine = make_engine(tmp_path, trader=trader, rpc=rpc)

    run(engine._do_open("MintA", "AAA", "", "CurveA", curve_at(5.0)))

    assert engine.positions == {}
    assert engine.failed_buys == 1
    assert engine.tokens_sniped == 0
    assert engine.balance_sol == pytest.approx(1.0)


def test_kauf_trotz_api_fehler_wird_gebucht_wenn_token_ankamen(tmp_path):
    """
    Wichtiger Sonderfall: Die API meldet eine Zeitueberschreitung, die
    Transaktion ging aber trotzdem durch. Der Bot muss die Position anlegen -
    sonst haelt er Token, von denen er nichts weiss.
    """
    rpc = FakeRpc(sol=0.84)
    rpc.token_balance = 500_000.0        # Token sind da!
    trader = FakeTrader(buy_ok=False)
    engine = make_engine(tmp_path, trader=trader, rpc=rpc, start_sol=1.0)

    run(engine._do_open("MintA", "AAA", "", "CurveA", curve_at(5.0)))

    assert "MintA" in engine.positions
    assert engine.positions["MintA"].tokens == pytest.approx(500_000.0)


def test_kauf_wird_abgelehnt_wenn_die_gebuehrenreserve_reissen_wuerde(tmp_path):
    """Ohne SOL-Reserve kaeme man aus den Positionen nicht mehr heraus."""
    rpc = FakeRpc(sol=0.16)   # 0.15 Einsatz wuerde nur 0.01 uebrig lassen
    trader = FakeTrader()
    engine = make_engine(tmp_path, trader=trader, rpc=rpc, start_sol=0.16)

    run(engine._do_open("MintA", "AAA", "", "CurveA", curve_at(5.0)))

    assert trader.buys == []          # gar nicht erst gesendet
    assert engine.positions == {}


# ---------------------------------------------------------------------------
# Verkauf
# ---------------------------------------------------------------------------
def _oeffne_position(engine, rpc, tokens=1_000_000.0, spent=0.15):
    """Legt direkt eine offene Position an (ohne den Kaufweg zu durchlaufen)."""
    from sniper.paper_engine import Position
    position = Position(
        mint="MintA", symbol="AAA", name="", bonding_curve="CurveA",
        tokens=tokens, tokens_initial=tokens,
        entry_price=spent / tokens, sol_spent=spent,
        last_price=spent / tokens,
    )
    engine.positions["MintA"] = position
    rpc.token_balance = tokens
    return position


def test_vollverkauf_bucht_den_echten_erloes(tmp_path):
    rpc = FakeRpc(sol=0.85)
    trader = FakeTrader()
    engine = make_engine(tmp_path, trader=trader, rpc=rpc, start_sol=1.0)
    position = _oeffne_position(engine, rpc)
    rpc.effects["SIG_SELL"] = TxEffect(success=True, sol_delta=0.20,
                                       token_delta=-1_000_000.0)

    async def szenario():
        async def nach_dem_verkauf():
            await asyncio.sleep(0.02)
            rpc.token_balance = 0.0
            rpc.sol_balance = 1.05        # 0.20 SOL eingenommen
        asyncio.create_task(nach_dem_verkauf())
        await engine._do_exit(position, curve_at(20.0), 1.0, ExitReason.TAKE_PROFIT)

    run(szenario())

    assert trader.sells == [("MintA", 100.0)]
    assert engine.positions == {}
    trade = engine.closed_trades[0]
    assert trade.sol_received == pytest.approx(0.20)
    assert trade.pnl_sol == pytest.approx(0.05)
    assert trade.exit_reason == ExitReason.TAKE_PROFIT


def test_teilverkauf_haelt_die_position_offen(tmp_path):
    rpc = FakeRpc(sol=0.85)
    trader = FakeTrader()
    engine = make_engine(tmp_path, trader=trader, rpc=rpc, start_sol=1.0)
    position = _oeffne_position(engine, rpc, tokens=1_000_000.0)
    rpc.effects["SIG_SELL"] = TxEffect(success=True, sol_delta=0.10,
                                       token_delta=-500_000.0)

    async def szenario():
        async def nach_dem_verkauf():
            await asyncio.sleep(0.02)
            rpc.token_balance = 500_000.0
            rpc.sol_balance = 0.95
        asyncio.create_task(nach_dem_verkauf())
        await engine._do_exit(position, curve_at(20.0), 0.5, ExitReason.PARTIAL_TP)

    run(szenario())

    assert trader.sells == [("MintA", 50.0)]
    assert "MintA" in engine.positions
    assert position.tokens == pytest.approx(500_000.0)
    assert position.partial_done is True
    assert position.sol_received == pytest.approx(0.10)


def test_fehlgeschlagener_verkauf_laesst_die_position_offen(tmp_path):
    """
    Der Verkauf ging nachweislich nicht durch (Token noch da, API meldet
    Fehler). Die Position darf NICHT als geschlossen gebucht werden - sonst
    haelt der Bot Token, die in keiner Liste mehr stehen.
    """
    rpc = FakeRpc(sol=0.85)
    trader = FakeTrader(sell_ok=False)
    engine = make_engine(tmp_path, trader=trader, rpc=rpc, start_sol=1.0)
    position = _oeffne_position(engine, rpc)

    run(engine._do_exit(position, curve_at(5.0), 1.0, ExitReason.STOP_LOSS))

    assert "MintA" in engine.positions
    assert engine.closed_trades == []
    assert engine.failed_sells == 1
    assert position.pending is False      # darf beim naechsten Tick neu versuchen


def test_verkauf_ohne_token_schliesst_die_position_ohne_neue_order(tmp_path):
    """
    Sonderfall: die Token sind nicht mehr da (ein frueherer Verkauf ging doch
    noch durch). Es darf keine zweite Order rausgehen.
    """
    rpc = FakeRpc(sol=1.0)
    trader = FakeTrader()
    engine = make_engine(tmp_path, trader=trader, rpc=rpc, start_sol=1.0)
    position = _oeffne_position(engine, rpc)
    rpc.token_balance = 0.0

    run(engine._do_exit(position, curve_at(5.0), 1.0, ExitReason.TIME_STOP))

    assert trader.sells == []
    assert engine.positions == {}
    assert len(engine.closed_trades) == 1


def test_kein_doppelter_verkaufsauftrag(tmp_path):
    """
    Waehrend ein Verkauf laeuft (pending), darf die Markt-Schleife keinen
    zweiten ausloesen - sonst wird doppelt verkauft.
    """
    engine = make_engine(tmp_path)
    position = _oeffne_position(engine, engine.rpc)

    assert engine.is_busy("MintA") is False
    position.pending = True
    assert engine.is_busy("MintA") is True

    # request_exit muss in diesem Zustand wirkungslos sein
    engine.request_exit(position, curve_at(5.0), fraction=1.0,
                        reason=ExitReason.STOP_LOSS)
    assert engine.trader.sells == []


# ---------------------------------------------------------------------------
# Not-Aus
# ---------------------------------------------------------------------------
def test_not_aus_greift_bei_verlustgrenze(tmp_path):
    """
    Bei -30 % GESAMTWERT muss der Bot abschalten.

    Gemessen wird bewusst der Gesamtwert (freies SOL + Wert der offenen
    Positionen), nicht das freie Guthaben: Letzteres sinkt schon dadurch, dass
    Positionen offen sind. Im Rauchtest meldete die alte Version so "-76.5 %
    Verlust", waehrend zwei Positionen auf +660 % und +711 % standen.
    """
    rpc = FakeRpc(sol=1.0)
    trader = FakeTrader()
    engine = make_engine(tmp_path, trader=trader, rpc=rpc, start_sol=1.0)
    stop_event_gesetzt = []

    class FakeEvent:
        def set(self):
            stop_event_gesetzt.append(True)

    engine.stop_event = FakeEvent()
    position = _oeffne_position(engine, rpc, spent=0.5)
    engine.balance_sol = 0.5             # 0.5 SOL stecken in der Position
    rpc.effects["SIG_SELL"] = TxEffect(success=True, sol_delta=0.15,
                                       token_delta=-1_000_000.0)

    async def szenario():
        async def nach_dem_verkauf():
            await asyncio.sleep(0.02)
            rpc.token_balance = 0.0
            rpc.sol_balance = 0.65       # -35 % vom Start
        asyncio.create_task(nach_dem_verkauf())
        await engine._do_exit(position, curve_at(1.0), 1.0, ExitReason.STOP_LOSS)

    run(szenario())

    # Position ist zu, es liegen nur noch 0.65 SOL auf der Wallet -> -35 %.
    engine.check_emergency_stop({})

    assert engine.emergency_stop is True
    assert "Verlustgrenze" in engine.emergency_reason
    assert stop_event_gesetzt == [True]


def test_not_aus_greift_nicht_bei_kleinem_verlust(tmp_path):
    rpc = FakeRpc(sol=1.0)
    engine = make_engine(tmp_path, rpc=rpc, start_sol=1.0)
    position = _oeffne_position(engine, rpc, spent=0.15)
    engine.balance_sol = 0.85
    rpc.effects["SIG_SELL"] = TxEffect(success=True, sol_delta=0.08,
                                       token_delta=-1_000_000.0)

    async def szenario():
        async def nach_dem_verkauf():
            await asyncio.sleep(0.02)
            rpc.token_balance = 0.0
            rpc.sol_balance = 0.93       # -7 %
        asyncio.create_task(nach_dem_verkauf())
        await engine._do_exit(position, curve_at(5.0), 1.0, ExitReason.STOP_LOSS)

    run(szenario())
    engine.check_emergency_stop({})

    assert engine.emergency_stop is False


def test_not_aus_zaehlt_offene_positionen_als_wert(tmp_path):
    """
    Steckt das Geld in offenen Positionen, ist es NICHT verloren. Der Not-Aus
    darf davon nicht ausgeloest werden - sonst schaltet der Bot ab, sobald er
    einfach nur viele Positionen offen hat.
    """
    rpc = FakeRpc(sol=1.0)
    engine = make_engine(tmp_path, rpc=rpc, start_sol=1.0)

    # Fast alles ist investiert: nur 0.1 SOL frei, der Rest in Positionen.
    # Die Tokenmenge wird aus dem echten Kurvenpreis abgeleitet, damit jede
    # Position tatsaechlich rund 0.15 SOL wert ist.
    zustand = curve_at(10.0)
    tokens_fuer_015_sol = 0.15 / zustand.price_sol

    engine.balance_sol = 0.1
    engine.positions.clear()
    for i in range(6):
        pos = _oeffne_position(engine, rpc, tokens=tokens_fuer_015_sol, spent=0.15)
        pos.mint = f"Mint{i}"
        pos.bonding_curve = f"Curve{i}"
        pos.last_price = zustand.price_sol
        engine.positions[pos.mint] = pos
    engine.positions.pop("MintA", None)

    # Freies Guthaben allein waere -90 % und wuerde faelschlich ausloesen.
    zustaende = {f"Curve{i}": zustand for i in range(6)}
    engine.check_emergency_stop(zustaende)

    assert engine.emergency_stop is False


def test_kein_kauf_mehr_nach_not_aus(tmp_path):
    engine = make_engine(tmp_path)
    engine.emergency_stop = True

    engine.request_open(mint="MintB", symbol="BBB", name="",
                        bonding_curve="CurveB", state=curve_at(5.0))

    assert engine.positions == {}
    assert engine.trader.buys == []


# ---------------------------------------------------------------------------
# Zusammenfassung
# ---------------------------------------------------------------------------
def test_zusammenfassung_nennt_die_betriebsart(tmp_path):
    engine = make_engine(tmp_path)
    text = "\n".join(engine.summary_lines())
    assert "ECHTGELD" in text
