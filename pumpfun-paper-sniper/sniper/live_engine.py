"""
live_engine.py -- ECHTGELD-Modus: Buchhaltung gegen die echte Bot-Wallet.

Dieses Modul ist das Gegenstueck zur paper_engine. Es bietet nach aussen
dieselben Methoden, fuehrt aber echte Kaeufe und Verkaeufe ueber die
PumpPortal-Lightning-API aus.

Aktiv nur, wenn in der config.yaml `live_trading: true` steht.

Die zwei wichtigsten Konstruktionsentscheidungen
------------------------------------------------
1. **Auftraege laufen im Hintergrund.**
   Ein Kauf besteht aus HTTPS-Anfrage + Warten auf die Bestaetigung durch die
   Blockchain - das kann 10-25 Sekunden dauern. Wuerde die Markt-Schleife
   solange blockieren, koennte sie in der Zeit keine andere Position
   ueberwachen. Deshalb wird jeder Auftrag als eigene Aufgabe gestartet, und
   die Position ist solange als `pending` markiert.

2. **Der Kontostand ist die Wahrheit, nicht die API-Antwort.**
   Eine Transaktion kann trotz "erfolgreich gesendet" auf der Blockchain
   scheitern (zu wenig Priority Fee, Slippage-Limit gerissen, Token schon
   migriert). Deshalb prueft der Bot nach jedem Auftrag den echten
   Token-Kontostand und den echten SOL-Kontostand der Wallet. Alles, was
   gebucht wird, ist gemessen - nicht geschaetzt.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from .config import Config
from .curve import CurveState
from .paper_engine import (
    ClosedTrade, EntrySnapshot, ExitReason, PaperEngine, Position,
)
from .pumpportal_trade import PumpPortalTrader
from .rpc import SolanaReadOnlyRpc

log = logging.getLogger(__name__)


class LiveEngine(PaperEngine):
    """
    Echtgeld-Variante. Erbt die komplette Buchhaltung, Statistik und
    CSV-Protokollierung von der PaperEngine und ersetzt nur die Stellen, an
    denen tatsaechlich gehandelt wird.
    """

    def __init__(
        self,
        cfg: Config,
        trader: PumpPortalTrader,
        rpc: SolanaReadOnlyRpc,
        wallet_pubkey: str,
        start_balance_sol: float,
    ) -> None:
        super().__init__(cfg)

        self.trader = trader
        self.rpc = rpc
        self.wallet = wallet_pubkey

        # Startkapital ist hier KEIN Wunschwert aus der config.yaml, sondern
        # das, was beim Start wirklich auf der Wallet lag.
        self.balance_sol = start_balance_sol
        self.start_balance_sol = start_balance_sol

        #: laufende Auftraege (damit beim Beenden nichts abgeschnitten wird)
        self._tasks: set[asyncio.Task] = set()
        #: Token, zu denen gerade ein Kaufauftrag laeuft
        self._opening: set[str] = set()

        #: Not-Aus ausgeloest?
        self.emergency_stop: bool = False
        self.emergency_reason: str = ""
        #: wird von main.py gesetzt, um den Bot komplett herunterzufahren
        self.stop_event: asyncio.Event | None = None

        #: Zaehler fuer Auftraege, die nicht durchgingen
        self.failed_buys: int = 0
        self.failed_sells: int = 0

    # ==================================================================
    # Schnittstelle fuer die Markt-Schleife
    # ==================================================================
    def is_busy(self, mint: str) -> bool:
        """True, solange zu diesem Token ein Auftrag unterwegs ist."""
        if mint in self._opening:
            return True
        position = self.positions.get(mint)
        return position is not None and position.pending

    def request_open(self, *, mint: str, symbol: str, name: str,
                     bonding_curve: str, state: CurveState,
                     snapshot: EntrySnapshot | None = None) -> None:
        """Startet einen Kauf im Hintergrund."""
        if self.emergency_stop or self.is_busy(mint) or mint in self.positions:
            return

        allowed, reason = self.can_open()
        if not allowed:
            log.info("Kauf %s abgelehnt: %s", symbol, reason)
            self.tokens_skipped += 1
            return

        self._opening.add(mint)
        self._spawn(self._do_open(mint, symbol, name, bonding_curve, state,
                                  snapshot or EntrySnapshot()))

    def request_add(self, position: Position, state: CurveState) -> None:
        """Startet einen Nachkauf im Hintergrund (siehe add_to_position)."""
        if self.emergency_stop or position.pending or self.is_busy(position.mint):
            return
        if position.entries >= self.cfg.advanced.max_entries_per_token:
            return
        self._opening.add(position.mint)
        self._spawn(self._do_open(
            position.mint, position.symbol, position.name,
            position.bonding_curve, state, position.entry_snapshot))

    def request_exit(self, position: Position, state: CurveState | None,
                     *, fraction: float, reason: str) -> None:
        """Startet einen Verkauf im Hintergrund."""
        if position.pending:
            return  # es laeuft schon ein Auftrag zu dieser Position
        position.pending = True
        self._spawn(self._do_exit(position, state, fraction, reason))

    async def shutdown(self, states: dict[str, CurveState | None]) -> None:
        """
        Beim Beenden: laufende Auftraege abwarten, dann alle offenen
        Positionen tatsaechlich verkaufen.
        """
        if self._tasks:
            log.info("Warte auf %d laufende(n) Auftrag/Auftraege ...", len(self._tasks))
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

        for position in list(self.positions.values()):
            try:
                position.pending = True
                await self._do_exit(
                    position, states.get(position.bonding_curve),
                    1.0, ExitReason.SHUTDOWN)
            except Exception as exc:  # noqa: BLE001
                log.exception("Position %s konnte nicht verkauft werden: %s",
                              position.symbol, exc)
                log.error(">>> WICHTIG: %s ggf. von Hand auf pump.fun verkaufen. "
                          "Mint: %s", position.symbol, position.mint)

    # ==================================================================
    # Kauf
    # ==================================================================
    async def _do_open(self, mint: str, symbol: str, name: str,
                       bonding_curve: str, state: CurveState,
                       snapshot: EntrySnapshot | None = None) -> None:
        """Fuehrt den Kauf aus und bucht das tatsaechliche Ergebnis."""
        try:
            size = self.cfg.position_size_sol

            # 1) Kontostaende VOR dem Kauf messen
            sol_before = await self.rpc.get_sol_balance(self.wallet)
            if sol_before is None:
                log.warning("Kauf %s abgebrochen: Kontostand nicht lesbar.", symbol)
                return

            reserve = self.cfg.live.min_wallet_balance_sol
            if sol_before - size < reserve:
                log.warning(
                    "Kauf %s abgebrochen: nach dem Kauf blieben nur %.4f SOL "
                    "uebrig, Mindestreserve fuer Gebuehren ist %.4f SOL.",
                    symbol, sol_before - size, reserve)
                return

            # 2) Auftrag senden
            log.info("KAUFAUFTRAG %s | %.4f SOL | Slippage %.0f%% | Prio %.5f SOL",
                     symbol, size, self.trader.slippage_pct,
                     self.trader.priority_fee_sol)
            result = await self.trader.buy(mint, size)

            # Auch bei Fehler weiterpruefen: eine Zeitueberschreitung heisst
            # NICHT, dass die Transaktion nicht doch durchging.
            if not result.ok:
                log.warning("Kaufauftrag %s meldet Fehler (%s) - pruefe trotzdem "
                            "den Kontostand.", symbol, result.error)

            # 3) Auf den echten Fill warten.
            #    Token-Bestaende sind pro Mint getrennt, deshalb ist diese
            #    Messung auch bei parallel laufenden Auftraegen zuverlaessig.
            tokens = await self._await_token_balance(mint, minimum=1e-9)
            if tokens <= 0:
                self.failed_buys += 1
                self.tokens_skipped += 1
                log.error("Kauf %s ist NICHT durchgegangen (keine Token "
                          "angekommen). Kein Geld gebunden.", symbol)
                return

            # 4) Tatsaechlich abgeflossenes SOL bestimmen.
            #    NICHT ueber die Differenz des Wallet-Kontostands: laufen
            #    mehrere Auftraege gleichzeitig, mischen sich deren Buchungen
            #    und der Wert waere falsch. Die Transaktion kennt nur sich selbst.
            sol_spent = await self._measure_sol_flow(
                result.signature, mint,
                fallback=-(size + self.trader.priority_fee_sol),
                sol_before=sol_before,
            )
            sol_spent = abs(sol_spent)

            # 5) Buchen. Existiert die Position schon, ist das ein Nachkauf:
            #    Menge und Einsatz kommen dazu, der Einstiegspreis wird zum
            #    gewichteten Mittel. So bleibt es eine Position pro Token und
            #    die Ausstiegslogik aendert sich nicht.
            bestehend = self.positions.get(mint)
            if bestehend is not None:
                dazu = max(0.0, tokens - bestehend.tokens)
                bestehend.tokens = tokens
                bestehend.tokens_initial += dazu
                bestehend.sol_spent += sol_spent
                bestehend.entries += 1
                if bestehend.tokens_initial > 0:
                    bestehend.entry_price = (
                        bestehend.sol_spent / bestehend.tokens_initial)
                log.info("NACHKAUF OK %s (%d. Einstieg) | %.4f SOL -> +%.0f Token "
                         "| neuer Mittelwert %.10f SOL | %s",
                         symbol, bestehend.entries, sol_spent, dazu,
                         bestehend.entry_price, result.solscan_url or "")
                self.balance_sol = max(0.0, self.balance_sol - sol_spent)
                self._write_csv_row(bestehend, event="ADD", reason="PYRAMID",
                                    price=state.price_sol, sol_flow=-sol_spent,
                                    tokens=dazu, pnl_sol=0.0, pnl_pct=0.0)
                return

            position = Position(
                mint=mint, symbol=symbol, name=name, bonding_curve=bonding_curve,
                tokens=tokens, tokens_initial=tokens,
                entry_price=sol_spent / tokens,
                sol_spent=sol_spent,
                last_price=state.price_sol,
                peak_price=state.price_sol,
                peak_real_sol=state.real_sol_reserves,
                entry_snapshot=snapshot or EntrySnapshot(),
            )
            self.positions[mint] = position
            self.tokens_sniped += 1
            self._recent_snipes.append(time.monotonic())
            self.balance_sol = max(0.0, self.balance_sol - sol_spent)

            log.info(
                "KAUF OK %s | %.4f SOL -> %.0f Token | Einstieg %.10f SOL | %s",
                symbol, sol_spent, tokens, position.entry_price,
                result.solscan_url or "(ohne Signatur)")

            self._write_csv_row(position, event="OPEN", reason="ENTRY",
                                price=position.entry_price, sol_flow=-sol_spent,
                                tokens=tokens, pnl_sol=0.0, pnl_pct=0.0)
        except Exception as exc:  # noqa: BLE001
            log.exception("Unerwarteter Fehler beim Kauf %s: %s", symbol, exc)
        finally:
            self._opening.discard(mint)

    # ==================================================================
    # Verkauf
    # ==================================================================
    async def _do_exit(self, position: Position, state: CurveState | None,
                       fraction: float, reason: str) -> None:
        """Fuehrt einen (Teil-)Verkauf aus und bucht das echte Ergebnis."""
        try:
            percent = max(1.0, min(100.0, fraction * 100.0))
            full_exit = percent >= 99.5

            tokens_before = await self.rpc.get_token_balance(self.wallet, position.mint)

            if tokens_before is not None and tokens_before <= 0:
                # Nichts mehr da - z.B. weil ein frueherer Verkauf doch noch
                # durchging. Position sauber schliessen, ohne neue Order.
                log.warning("%s: keine Token mehr in der Wallet, Position wird "
                            "nur noch verbucht.", position.symbol)
                self._book_close(position, 0.0, state, reason)
                return

            log.info("VERKAUFSAUFTRAG %s (%s) | %.0f%% der Position",
                     position.symbol, reason, percent)
            result = await self.trader.sell_percent(position.mint, percent)
            if not result.ok:
                log.warning("Verkaufsauftrag %s meldet Fehler (%s) - pruefe "
                            "trotzdem den Kontostand.", position.symbol, result.error)

            # Auf die Wirkung warten: der Token-Bestand muss sinken.
            target = 0.0 if full_exit else (tokens_before or 0.0) * (1.0 - percent / 100.0)
            tokens_after = await self._await_token_balance(
                position.mint, maximum=max(target * 1.05, 1e-9))

            sold_something = (tokens_before or 0.0) - tokens_after > 0

            # Erloes exakt aus der Transaktion lesen (siehe Kommentar im Kauf).
            sol_received = 0.0
            if sold_something or result.ok:
                sol_received = max(0.0, await self._measure_sol_flow(
                    result.signature, position.mint, fallback=0.0))
                self.balance_sol += sol_received

            if not sold_something and not result.ok:
                # Verkauf ist nachweislich nicht durchgegangen.
                self.failed_sells += 1
                log.error(
                    "VERKAUF %s FEHLGESCHLAGEN (%s). Position bleibt offen und "
                    "wird beim naechsten Tick erneut geprueft.",
                    position.symbol, result.error)
                if reason == ExitReason.SHUTDOWN:
                    log.error(">>> WICHTIG: %s manuell auf pump.fun verkaufen! "
                              "Mint: %s", position.symbol, position.mint)
                return

            position.tokens = tokens_after
            position.sol_received += sol_received

            if full_exit or tokens_after <= 0:
                self._book_close(position, sol_received, state, reason)
            else:
                position.partial_done = True
                log.info("TEILVERKAUF OK %s | +%.4f SOL | Rest %.0f Token | %s",
                         position.symbol, sol_received, tokens_after,
                         result.solscan_url or "")
                self._write_csv_row(
                    position, event="PARTIAL", reason=reason,
                    price=state.price_sol if state else position.last_price,
                    sol_flow=sol_received,
                    tokens=(tokens_before or 0.0) - tokens_after,
                    pnl_sol=0.0, pnl_pct=0.0)
        except Exception as exc:  # noqa: BLE001
            log.exception("Unerwarteter Fehler beim Verkauf %s: %s",
                          position.symbol, exc)
        finally:
            position.pending = False

    def _book_close(self, position: Position, sol_received: float,
                    state: CurveState | None, reason: str) -> None:
        """Position aus der Liste nehmen und in die Historie schreiben."""
        pnl_sol = position.sol_received - position.sol_spent
        pnl_pct = (pnl_sol / position.sol_spent * 100.0) if position.sol_spent else 0.0
        exit_price = state.price_sol if (state and state.is_tradable) else position.last_price

        trade = ClosedTrade(
            symbol=position.symbol, mint=position.mint, exit_reason=reason,
            entry_price=position.entry_price, exit_price=exit_price,
            sol_spent=position.sol_spent, sol_received=position.sol_received,
            pnl_sol=pnl_sol, pnl_pct=pnl_pct, hold_sec=position.age_sec,
            opened_wall=position.opened_wall,
            closed_wall=datetime.now(timezone.utc),
            had_partial=position.partial_done,
        )
        self.closed_trades.append(trade)
        self.positions.pop(position.mint, None)

        log.info("VERKAUF OK %s (%s) | +%.4f SOL | P&L %+.4f SOL (%+.1f%%) | "
                 "Haltedauer %.0fs | Wallet %.4f SOL",
                 position.symbol, reason, sol_received, pnl_sol, pnl_pct,
                 trade.hold_sec, self.balance_sol)

        self._write_csv_row(position, event="CLOSE", reason=reason,
                            price=exit_price, sol_flow=sol_received,
                            tokens=position.sol_received,
                            pnl_sol=pnl_sol, pnl_pct=pnl_pct)


    # ==================================================================
    # Not-Aus
    # ==================================================================
    def check_emergency_stop(
        self, states: dict[str, CurveState | None] | None = None
    ) -> None:
        """
        Prueft, ob die Verlustgrenze aus der config.yaml gerissen ist. Wenn ja,
        wird der Bot heruntergefahren - offene Positionen verkauft er dabei noch.

        Verglichen wird der GESAMTWERT (freies SOL + Wert der offenen
        Positionen), nicht das freie Guthaben.

        Das war urspruenglich anders und war ein ernster Fehler: Freies SOL
        sinkt schon dadurch, dass Positionen offen sind - das Geld ist nicht
        weg, es steckt nur im Markt. Bei 10 Positionen zu 0.15 SOL sind 1.5 SOL
        gebunden; der Not-Aus haette also sofort ausgeloest und alles zum
        schlechtest moeglichen Zeitpunkt verkauft. Im Rauchtest passierte genau
        das: gemeldet wurden "-76.5 % Verlust", waehrend zwei der Positionen
        auf +660 % und +711 % standen.
        """
        if self.emergency_stop:
            return

        limit_pct = self.cfg.live.max_total_loss_pct
        if limit_pct <= 0 or self.start_balance_sol <= 0:
            return

        gesamtwert = self.equity_sol(states or {})
        loss_pct = (1.0 - gesamtwert / self.start_balance_sol) * 100.0
        if loss_pct < limit_pct:
            return

        self.emergency_stop = True
        self.emergency_reason = (
            f"Verlustgrenze erreicht: {loss_pct:.1f} % vom Startkapital "
            f"({self.start_balance_sol:.4f} -> {gesamtwert:.4f} SOL Gesamtwert). "
            f"Grenze war {limit_pct:.0f} %."
        )
        log.error("=" * 70)
        log.error("NOT-AUS: %s", self.emergency_reason)
        log.error("Der Bot verkauft offene Positionen und beendet sich.")
        log.error("=" * 70)

        if self.stop_event is not None:
            self.stop_event.set()

    # ==================================================================
    # Hilfsfunktionen
    # ==================================================================
    async def _measure_sol_flow(
        self, signature: str, mint: str, *, fallback: float,
        sol_before: float | None = None,
    ) -> float:
        """
        Ermittelt, wie viel SOL eine bestimmte Transaktion bewegt hat.
        Negativ = abgeflossen (Kauf), positiv = zugeflossen (Verkauf).

        Reihenfolge der Versuche:
          1. Die Transaktion nachschlagen (`getTransaction`). Exakt und auch
             dann korrekt, wenn parallel andere Auftraege laufen.
          2. Klappt das nicht (RPC unterstuetzt es nicht, Transaktion nicht
             auffindbar, keine Signatur), wird der Kontostand herangezogen
             bzw. der uebergebene Schaetzwert benutzt. Das ist ungenauer,
             aber besser als gar keine Buchung.
        """
        if signature:
            effect = await self.rpc.get_transaction_effect(
                signature, self.wallet, mint,
                timeout_sec=self.cfg.live.fill_confirm_timeout_sec,
                poll_interval_sec=self.cfg.live.fill_poll_interval_sec,
            )
            if effect is not None:
                if not effect.success:
                    log.warning("Transaktion %s ist on-chain fehlgeschlagen "
                                "(Gebuehren fallen trotzdem an).", signature[:16])
                return effect.sol_delta

        # --- Notnagel ---
        if sol_before is not None:
            sol_now = await self.rpc.get_sol_balance(self.wallet)
            if sol_now is not None:
                log.debug("Geldfluss aus Kontostand geschaetzt (ungenau bei "
                          "parallelen Auftraegen).")
                return sol_now - sol_before
        log.warning("Geldfluss konnte nicht gemessen werden - es wird mit "
                    "einem Schaetzwert gebucht (%.5f SOL).", fallback)
        return fallback

    async def _await_token_balance(
        self, mint: str, *, minimum: float | None = None,
        maximum: float | None = None,
    ) -> float:
        """
        Wartet, bis der Token-Kontostand die Erwartung erfuellt - oder bis die
        Zeit abgelaufen ist.

        `minimum` -> warten, bis mindestens so viele Token da sind (Kauf)
        `maximum` -> warten, bis hoechstens noch so viele da sind (Verkauf)

        Gibt den zuletzt gemessenen Bestand zurueck. Laeuft die Zeit ab, ist
        das der aktuelle Stand - der Bot bucht dann das, was wirklich da ist.
        """
        deadline = time.monotonic() + self.cfg.live.fill_confirm_timeout_sec
        interval = self.cfg.live.fill_poll_interval_sec
        last_seen = 0.0

        while time.monotonic() < deadline:
            balance = await self.rpc.get_token_balance(self.wallet, mint)
            if balance is not None:
                last_seen = balance
                if minimum is not None and balance >= minimum:
                    return balance
                if maximum is not None and balance <= maximum:
                    return balance
            await asyncio.sleep(interval)

        log.warning("Bestaetigung fuer %s nicht innerhalb von %.0fs erhalten "
                    "(zuletzt %.0f Token).", mint[:8],
                    self.cfg.live.fill_confirm_timeout_sec, last_seen)
        return last_seen

    def _spawn(self, coro) -> None:
        """Startet eine Hintergrundaufgabe und raeumt sie danach wieder auf."""
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # ==================================================================
    # Abschlussbericht
    # ==================================================================
    def summary_lines(self) -> list[str]:
        lines = super().summary_lines()
        lines.insert(0, "Betriebsart       : ECHTGELD (PumpPortal Lightning)")
        if self.failed_buys or self.failed_sells:
            lines.append(f"Fehlgeschlagene Auftraege: {self.failed_buys} Kauf / "
                         f"{self.failed_sells} Verkauf")
        if self.emergency_stop:
            lines.append(f"NOT-AUS: {self.emergency_reason}")
        return lines
