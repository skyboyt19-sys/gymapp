"""
market.py -- die Herzschlag-Schleife des Bots.

Hier laufen alle Teile zusammen:

    Feed (neue Token)  ->  Kandidaten im Beobachtungsfenster
                              |
                              v
    RPC-Poll alle `rpc_poll_ms` ms: Kurse aller beobachteten Token holen
                              |
              +---------------+---------------+
              v                               v
    offene Positionen: Ausstieg pruefen   Kandidaten: Einstieg pruefen
              |                               |
              v                               v
                        paper_engine (Buchung)

Alles pro Token in try/except: ein einzelner kaputter Token darf nie den
ganzen Bot mitreissen.
"""

from __future__ import annotations

import asyncio
import logging
import time

from .config import Config
from .curve import CurveState
from .feed import NewTokenEvent
from .paper_engine import EntrySnapshot, PaperEngine, Position
from .rpc import SolanaReadOnlyRpc
from .strategy import (
    Candidate,
    FlowTracker,
    decide_exit,
    evaluate_entry,
    evaluate_survivor_entry,
    make_candidate,
    should_add_to_position,
)

log = logging.getLogger(__name__)


class MarketLoop:
    """Beobachtet Kandidaten, verwaltet Positionen und taktet die RPC-Abfragen."""

    def __init__(
        self,
        cfg: Config,
        engine: PaperEngine,
        rpc: SolanaReadOnlyRpc,
        queue: "asyncio.Queue[NewTokenEvent]",
    ) -> None:
        self.cfg = cfg
        self.engine = engine
        self.rpc = rpc
        self.queue = queue

        #: Token im Beobachtungsfenster (mint -> Candidate)
        self.candidates: dict[str, Candidate] = {}
        #: Fluss-Historie je offener Position (mint -> FlowTracker)
        self.position_flows: dict[str, FlowTracker] = {}
        #: zuletzt bekannter Zustand je Bonding-Curve-Adresse
        self.last_states: dict[str, CurveState | None] = {}

        #: Statistik fuers Dashboard
        self.ticks: int = 0
        self.last_tick_at: float = 0.0
        self.last_tick_duration_ms: float = 0.0

    # ------------------------------------------------------------------
    # Hauptschleife
    # ------------------------------------------------------------------
    async def run(self, stop_event: asyncio.Event) -> None:
        """Laeuft, bis `stop_event` gesetzt wird."""
        interval = self.cfg.rpc_poll_sec
        loop = asyncio.get_running_loop()

        while not stop_event.is_set():
            started = loop.time()
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - die Schleife darf nie sterben
                log.exception("Unerwarteter Fehler im Markt-Tick: %s", exc)

            self.last_tick_duration_ms = (loop.time() - started) * 1000.0
            self.last_tick_at = time.monotonic()
            self.ticks += 1

            # Restzeit bis zum naechsten Poll abwarten - aber sofort abbrechen,
            # wenn der Bot beendet wird.
            remaining = max(0.0, interval - (loop.time() - started))
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=remaining)
            except asyncio.TimeoutError:
                pass  # normaler Fall: Wartezeit ist abgelaufen

        log.info("Markt-Schleife beendet.")

    async def _tick(self) -> None:
        """Ein kompletter Durchlauf: neue Token aufnehmen, Kurse holen, handeln."""
        now = time.monotonic()

        # 1) Neue Token aus dem Feed uebernehmen
        self._drain_feed_queue()

        # 2) Welche Bonding-Curve-Accounts brauchen wir diesmal?
        addresses = self._collect_addresses()
        if not addresses:
            return

        # 3) Kurse holen (ein einziger RPC-Aufruf pro 100 Accounts)
        states = await self.rpc.fetch_curve_states(addresses)
        for address, state in states.items():
            # Nur echte Antworten merken - bei einem RPC-Aussetzer behalten wir
            # den alten Zustand, statt ihn mit None zu ueberschreiben.
            if state is not None:
                self.last_states[address] = state

        # 4) Offene Positionen zuerst - Ausstiege sind wichtiger als Einstiege
        self._process_positions(states, now)

        # 5) Kandidaten aktualisieren und ggf. kaufen
        self._process_candidates(states, now)

        # 6) Verlustgrenze pruefen (nur Echtgeld-Modus).
        #    Hier und nicht in der Engine, weil nur die Markt-Schleife die
        #    aktuellen Kurse hat - und ohne die laesst sich der Gesamtwert der
        #    offenen Positionen nicht bestimmen.
        self.engine.check_emergency_stop(self.last_states)

        # 7) Aufraeumen
        self._cleanup(now)

    # ------------------------------------------------------------------
    # Feed -> Kandidaten
    # ------------------------------------------------------------------
    def _drain_feed_queue(self) -> None:
        """Holt alle inzwischen eingetroffenen Launch-Events aus der Queue."""
        while True:
            try:
                event = self.queue.get_nowait()
            except asyncio.QueueEmpty:
                return

            try:
                self.engine.tokens_scanned += 1

                # Schon als Position oder Kandidat bekannt? Dann ignorieren.
                if event.mint in self.candidates or event.mint in self.engine.positions:
                    continue

                candidate = make_candidate(event)
                self.candidates[event.mint] = candidate
                log.debug("Neuer Kandidat: %s (%s)", event.symbol, event.mint[:8])
            except Exception as exc:  # noqa: BLE001
                log.warning("Launch-Event konnte nicht verarbeitet werden: %s", exc)

    def _collect_addresses(self) -> list[str]:
        """
        Sammelt alle Bonding-Curve-Adressen, deren Kurs dieser Tick braucht:
        alle Kandidaten im Fenster + alle offenen Positionen.
        Doppelte werden entfernt, die Reihenfolge bleibt stabil.
        """
        now = time.monotonic()
        seen: dict[str, None] = {}

        # Offene Positionen immer - da zaehlt jede Sekunde.
        for position in self.engine.positions.values():
            if position.bonding_curve:
                seen.setdefault(position.bonding_curve, None)

        # Kandidaten nur, wenn sie faellig sind. In der Survivor-Strategie
        # werden Token ueber viele Minuten beobachtet; wuerde man alle bei
        # jedem Tick abfragen, waere jede RPC sofort im Rate-Limit.
        for candidate in self.candidates.values():
            if not candidate.bonding_curve:
                continue
            if candidate.next_poll_at > now:
                continue
            seen.setdefault(candidate.bonding_curve, None)
        return list(seen.keys())

    # ------------------------------------------------------------------
    # Offene Positionen
    # ------------------------------------------------------------------
    def _process_positions(
        self, states: dict[str, CurveState | None], now: float
    ) -> None:
        """Prueft fuer jede offene Position die Ausstiegsregeln."""
        # Kopie der Werte, weil wir waehrend der Schleife Positionen entfernen.
        for position in list(self.engine.positions.values()):
            try:
                self._process_one_position(position, states, now)
            except Exception as exc:  # noqa: BLE001
                log.exception("Fehler bei Position %s: %s", position.symbol, exc)

    def _process_one_position(
        self, position: Position, states: dict[str, CurveState | None], now: float
    ) -> None:
        # Im Echtgeld-Modus kann ein Verkaufsauftrag mehrere Sekunden brauchen,
        # bis er auf der Blockchain bestaetigt ist. Solange darf keine zweite
        # Order zur selben Position rausgehen - sonst wird doppelt verkauft.
        if self.engine.is_busy(position.mint):
            return

        state = states.get(position.bonding_curve)
        if state is None:
            # RPC hat fuer diesen Account nichts geliefert -> letzten bekannten
            # Zustand verwenden, damit z.B. der Zeitstopp trotzdem greifen kann.
            state = self.last_states.get(position.bonding_curve)

        # Ist die Kurve migriert, sind ihre Reserven kein sinnvoller Kurs mehr.
        # Dann NICHT den zuletzt gesehenen (gueltigen) Kurs ueberschreiben -
        # der wird beim Schliessen fuer die Bewertung des Restbestands
        # gebraucht. `decide_exit` schliesst die Position ohnehin sofort.
        usable = state is not None and state.is_tradable

        # -- Kursverlust seit dem letzten Tick berechnen (fuer den Rug-Exit) --
        previous_price = position.last_price
        tick_drop_pct = 0.0
        if usable and previous_price > 0:
            new_price = state.price_sol  # type: ignore[union-attr]
            if new_price < previous_price:
                tick_drop_pct = (1.0 - new_price / previous_price) * 100.0

        # -- Kurs und Fluss-Historie aktualisieren --
        if usable:
            self.engine.update_position_price(position, state.price_sol)  # type: ignore[union-attr]
            # Hoechststand des echten SOL mitfuehren - Referenz fuer den
            # Drain-Notausstieg.
            if state.real_sol_reserves > position.peak_real_sol:  # type: ignore[union-attr]
                position.peak_real_sol = state.real_sol_reserves  # type: ignore[union-attr]
            flow = self.position_flows.setdefault(position.mint, FlowTracker())
            flow.add(now, state.real_sol_reserves)  # type: ignore[union-attr]

        flow = self.position_flows.get(position.mint)
        net_flow = (
            flow.net_flow_sol(self.cfg.advanced.net_sell_flip_window_sec, now)
            if flow is not None else 0.0
        )

        # -- Entscheidung --
        decision = decide_exit(
            position, state, self.cfg,
            tick_drop_pct=tick_drop_pct,
            net_flow_sol=net_flow,
        )

        if decision.action == "hold":
            # Position bleibt offen - dann ist noch die Frage, ob nachgekauft
            # werden soll. Bewusst NACH der Ausstiegspruefung: Wer gerade
            # rausmuesste, darf auf keinen Fall nachlegen.
            darf, grund = should_add_to_position(
                position, state, self.cfg, net_flow_sol=net_flow)
            if darf and state is not None:
                log.info("Nachkauf %s: %s", position.symbol, grund)
                self.engine.request_add(position, state)
            return

        log.info("Exit %s (%s): %s", position.symbol, decision.reason, decision.detail)
        self.engine.request_exit(
            position, state,
            fraction=decision.fraction if decision.action == "partial" else 1.0,
            reason=decision.reason,
        )

    # ------------------------------------------------------------------
    # Kandidaten
    # ------------------------------------------------------------------
    def _process_candidates(
        self, states: dict[str, CurveState | None], now: float
    ) -> None:
        """Aktualisiert die Messwerte und entscheidet am Fensterende ueber den Kauf."""
        for candidate in list(self.candidates.values()):
            try:
                self._process_one_candidate(candidate, states, now)
            except Exception as exc:  # noqa: BLE001
                log.exception("Fehler bei Kandidat %s: %s", candidate.event.symbol, exc)
                # Kaputten Kandidaten entfernen, damit der Fehler sich nicht
                # bei jedem Tick wiederholt.
                self.candidates.pop(candidate.mint, None)
                self.engine.tokens_skipped += 1

    def _process_one_candidate(
        self, candidate: Candidate, states: dict[str, CurveState | None], now: float
    ) -> None:
        # Wurde dieser Kandidat diesmal ueberhaupt abgefragt?
        frisch = candidate.bonding_curve in states
        state = states.get(candidate.bonding_curve)
        if state is None:
            state = self.last_states.get(candidate.bonding_curve)
        if state is not None and frisch:
            candidate.on_tick(state, now)

        if self.cfg.entry_mode == "survivor":
            self._process_survivor_candidate(candidate, now)
            return

        # ---- Ausbruchsstrategie (momentum): einmal pruefen, dann verwerfen ----
        if candidate.age_sec < self.cfg.signal_window_sec:
            return

        # --- Fenster vorbei: Entscheidung ---
        self.candidates.pop(candidate.mint, None)

        decision = evaluate_entry(candidate, self.cfg)
        if not decision.buy:
            self.engine.tokens_skipped += 1
            log.debug("SKIP %s: %s", candidate.event.symbol, decision.reason)
            return

        assert candidate.last_state is not None  # von evaluate_entry garantiert
        log.info("SNIPE %s: %s", candidate.event.symbol, decision.reason)

        # Der Net-Sell-Flip bekommt eine FRISCHE Fluss-Historie, die beim
        # Einstieg beginnt.
        #
        # Vorher wurde die Historie aus dem Beobachtungsfenster uebernommen -
        # mit der Folge, dass der Flip schon beim allerersten Tick nach dem Kauf
        # ausloesen konnte, obwohl er sich auf Bewegungen von VOR dem Kauf
        # bezog. Im Betrieb fuehrte das zu Trades, die nach einer Sekunde
        # wieder geschlossen waren und nur doppelte Gebuehren gekostet haben.
        #
        # Muss VOR dem Kaufauftrag passieren: im Echtgeld-Modus laeuft der Kauf
        # im Hintergrund, und die Position existiert erst danach.
        flow = FlowTracker()
        flow.add(now, candidate.last_state.real_sol_reserves)
        self.position_flows[candidate.mint] = flow

        # Die Messwerte, die zum Kauf gefuehrt haben, wandern mit in die
        # trades.csv - sonst kann man hinterher nicht auswerten, unter welchen
        # Bedingungen Trades funktionieren und unter welchen nicht.
        snapshot = EntrySnapshot(
            progress_pct=candidate.last_state.progress_pct(
                self.cfg.advanced.initial_real_token_reserves),
            net_buy_sol=candidate.net_buy_volume_sol,
            momentum_pct=candidate.price_gain_pct,
            dev_holding_pct=candidate.event.dev_holding_pct,
        )

        self.engine.request_open(
            mint=candidate.mint,
            symbol=candidate.event.symbol,
            name=candidate.event.name,
            bonding_curve=candidate.bonding_curve,
            state=candidate.last_state,
            snapshot=snapshot,
        )

    def _process_survivor_candidate(self, candidate: Candidate, now: float) -> None:
        """
        Watchlist-Logik der "Ueberlebenden"-Strategie.

        Anders als beim Ausbruchskauf wird ein Token nicht einmal geprueft und
        dann verworfen, sondern ueber Minuten beobachtet. Gekauft wird, sobald
        er alt genug ist, nicht leerlaeuft und frischen Zufluss zeigt.
        """
        sv = self.cfg.survivor

        # Naechste Abfrage einplanen - deutlich seltener als bei Positionen.
        candidate.next_poll_at = now + sv.watchlist_poll_sec

        # Zu alt: von der Watchlist nehmen.
        if candidate.age_sec > sv.max_age_sec:
            self.candidates.pop(candidate.mint, None)
            self.engine.tokens_skipped += 1
            return

        state = candidate.last_state
        if state is None:
            return  # noch keine Kursdaten - weiter beobachten

        # Endgueltig tot oder migriert: raus aus der Watchlist.
        if not state.is_tradable:
            self.candidates.pop(candidate.mint, None)
            self.engine.tokens_skipped += 1
            return

        decision = evaluate_survivor_entry(candidate, self.cfg)
        if not decision.buy:
            # Noch nicht so weit - der Token bleibt auf der Watchlist, bis er
            # zu alt wird. Genau das ist der Sinn der Strategie.
            log.debug("Watchlist %s: %s", candidate.event.symbol, decision.reason)
            return

        self.candidates.pop(candidate.mint, None)
        log.info("SNIPE (Ueberlebender) %s: %s",
                 candidate.event.symbol, decision.reason)

        flow = FlowTracker()
        flow.add(now, state.real_sol_reserves)
        self.position_flows[candidate.mint] = flow

        self.engine.request_open(
            mint=candidate.mint,
            symbol=candidate.event.symbol,
            name=candidate.event.name,
            bonding_curve=candidate.bonding_curve,
            state=state,
            snapshot=EntrySnapshot(
                progress_pct=state.progress_pct(
                    self.cfg.advanced.initial_real_token_reserves),
                net_buy_sol=candidate.flow.net_flow_sol(sv.inflow_window_sec),
                momentum_pct=candidate.price_gain_pct,
                dev_holding_pct=candidate.event.dev_holding_pct,
            ),
        )

    # ------------------------------------------------------------------
    # Aufraeumen
    # ------------------------------------------------------------------
    def _cleanup(self, now: float) -> None:
        """
        Entfernt Kandidaten, die aus irgendeinem Grund haengen geblieben sind
        (z.B. RPC kennt den Account dauerhaft nicht). Reines Sicherheitsnetz
        gegen wachsenden Speicherverbrauch bei langen Laufzeiten.
        """
        if self.cfg.entry_mode == "survivor":
            # Watchlist-Groesse begrenzen: Bei ~50 Launches pro Minute und 15
            # Minuten Beobachtungsdauer waeren das sonst hunderte Accounts,
            # die jede RPC ins Rate-Limit treiben. Die aeltesten fliegen zuerst
            # raus - die sind ihrer Entscheidung ohnehin am naechsten.
            grenze = self.cfg.survivor.watchlist_max_tokens
            if len(self.candidates) > grenze:
                zu_alt = sorted(self.candidates.values(),
                                key=lambda c: c.age_sec, reverse=True)
                for candidate in zu_alt[:len(self.candidates) - grenze]:
                    self.candidates.pop(candidate.mint, None)
                    self.engine.tokens_skipped += 1
        else:
            max_lifetime = self.cfg.advanced.candidate_max_lifetime_sec
            for mint, candidate in list(self.candidates.items()):
                if candidate.age_sec > max_lifetime:
                    self.candidates.pop(mint, None)
                    self.engine.tokens_skipped += 1
                    log.debug("Kandidat %s verworfen (Zeitueberschreitung).",
                              candidate.event.symbol)

        # Fluss-Historien ohne zugehoerige Position wegwerfen. Achtung: einen
        # gerade laufenden Kaufauftrag nicht mitloeschen - dessen Position gibt
        # es noch nicht, die Historie wird aber gleich gebraucht.
        for mint in list(self.position_flows.keys()):
            if mint not in self.engine.positions and not self.engine.is_busy(mint):
                self.position_flows.pop(mint, None)

    # ------------------------------------------------------------------
    # Herunterfahren
    # ------------------------------------------------------------------
    async def close_all_positions(self) -> None:
        """
        Schliesst beim Beenden (Strg+C) alle offenen Positionen.

        Im Simulationsmodus ist das eine Buchung, im Echtgeld-Modus ein echter
        Verkauf. Vorher wird noch einmal versucht, frische Kurse zu holen -
        klappt das nicht, gilt der letzte bekannte Stand.
        """
        if not self.engine.positions:
            return

        log.info("Schliesse %d offene Position(en) ...", len(self.engine.positions))

        addresses = [
            position.bonding_curve for position in self.engine.positions.values()
        ]
        states: dict[str, CurveState | None] = {}
        try:
            states = await asyncio.wait_for(
                self.rpc.fetch_curve_states(addresses),
                timeout=self.cfg.advanced.rpc_timeout_sec,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Letzter Kursabruf fehlgeschlagen (%s) - nutze letzte "
                        "bekannte Kurse.", exc)

        # Fehlende Kurse mit dem letzten bekannten Stand auffuellen und die
        # Positionen darauf aktualisieren.
        for position in self.engine.positions.values():
            state = states.get(position.bonding_curve) \
                or self.last_states.get(position.bonding_curve)
            states[position.bonding_curve] = state
            if state is not None and state.is_tradable:
                self.engine.update_position_price(position, state.price_sol)

        await self.engine.shutdown(states)
