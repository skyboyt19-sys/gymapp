"""
keep_awake.py -- verhindert, dass Windows waehrend des Betriebs einschlaeft.

Warum das wichtig ist
---------------------
Der Bot braucht durchgehend Internet: WebSocket-Feed fuer neue Token,
RPC-Abfragen fuer die Kurse. Geht der Rechner in den Energiesparmodus, friert
er mitten im Handel ein.

Im Simulationsmodus ist das nur aergerlich - die Messreihe hat dann ein Loch.

Im ECHTGELD-Modus ist es gefaehrlich: Offene Positionen liegen dann ohne jede
Ueberwachung auf der Wallet. Kein Stop-Loss, kein Trailing, kein Zeitstopp -
alles das setzt voraus, dass der Bot laeuft und Kurse abfragt. Ein Token kann
in der Zwischenzeit auf null gehen, ohne dass irgendetwas reagiert.

Was hier passiert
-----------------
Windows bekommt ueber `SetThreadExecutionState` gesagt: "Solange dieses
Programm laeuft, bitte nicht schlafen legen."

Der Bildschirm darf trotzdem ausgehen - dafuer waere zusaetzlich
ES_DISPLAY_REQUIRED noetig, und einen Monitor die ganze Nacht laufen zu lassen
braucht niemand.

Auf Linux und macOS tut dieses Modul nichts (dort startet man Dauerlaeufer
ueblicherweise als Dienst). Es schlaegt auch nie fehl: Klappt der Aufruf
nicht, laeuft der Bot normal weiter - nur eben ohne diese Absicherung.
"""

from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)

# Flags aus der Windows-API (winbase.h):
_ES_CONTINUOUS = 0x80000000        # gilt, bis es widerrufen wird
_ES_SYSTEM_REQUIRED = 0x00000001   # System wach halten (Bildschirm darf aus)


class KeepAwake:
    """
    Kontextmanager. Innerhalb des `with`-Blocks bleibt der Rechner wach.

        with KeepAwake(aktiv=True):
            ...  # hier laeuft der Bot

    Nach dem Block gilt wieder die normale Energieeinstellung von Windows.
    """

    def __init__(self, aktiv: bool = True) -> None:
        self.aktiv = aktiv
        self.wirksam = False   # True, wenn Windows den Wunsch akzeptiert hat

    def __enter__(self) -> "KeepAwake":
        if not self.aktiv or not sys.platform.startswith("win"):
            return self

        try:
            import ctypes

            ergebnis = ctypes.windll.kernel32.SetThreadExecutionState(  # type: ignore[attr-defined]
                _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED
            )
            # Rueckgabe 0 bedeutet: Windows hat den Wunsch abgelehnt.
            self.wirksam = ergebnis != 0
            if self.wirksam:
                log.info("Energiesparmodus ist waehrend des Betriebs deaktiviert "
                         "(der Bildschirm darf ausgehen).")
            else:
                log.warning("Windows hat das Wachhalten abgelehnt - der Rechner "
                            "koennte einschlafen und den Bot anhalten.")
        except Exception as exc:  # noqa: BLE001 - darf den Start nie verhindern
            log.warning("Wachhalten nicht moeglich (%s). Bitte in den "
                        "Windows-Energieoptionen den Ruhezustand auf 'Nie' "
                        "stellen.", exc)
        return self

    def __exit__(self, *_exc: object) -> None:
        if not self.wirksam:
            return
        try:
            import ctypes

            # Nur ES_CONTINUOUS setzen = die Anforderung wieder zuruecknehmen.
            ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)  # type: ignore[attr-defined]
            log.info("Energiesparmodus wieder freigegeben.")
        except Exception:  # noqa: BLE001
            pass
