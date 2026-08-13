"""
auswertung.py -- wertet die trades.csv aus und sagt, woran es liegt.

Start unter Windows:  Doppelklick auf  auswertung.bat

Das Skript handelt nichts und aendert nichts. Es liest nur die trades.csv und
rechnet aus:

  1. Wie sieht das Gesamtergebnis aus - und welche Trefferquote braeuchte die
     Strategie ueberhaupt, um bei null herauszukommen?
  2. Welcher Ausstiegsgrund kostet das meiste Geld?
  3. Bei welchen EINSTIEGSBEDINGUNGEN hat es funktioniert und bei welchen
     nicht? (Braucht die Spalten progress_pct, kaufdruck_sol, momentum_pct -
     die schreibt der Bot seit August 2026 mit.)

Wichtige Warnung zur Benutzung
------------------------------
Die Versuchung ist gross, jetzt so lange an den Filtern zu drehen, bis diese
eine Datei ein Plus zeigt. Das ist kein besserer Bot, das ist Auswendiglernen
der Vergangenheit ("Overfitting") - live verliert er danach genauso.

Faustregeln:
  * Nur Gruppen mit mindestens ~20 Trades ernst nehmen. Darunter ist alles
    Zufall.
  * Nur Unterschiede uebernehmen, die deutlich sind (etwa Faktor 2 im
    Ergebnis), nicht jede kleine Abweichung.
  * Nach jeder Aenderung einen NEUEN Lauf abwarten und dort pruefen, ob der
    Effekt bleibt. Nur das zaehlt.
"""

from __future__ import annotations

import csv
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

PROJECT_ROOT = Path(__file__).resolve().parent

#: Unter so vielen Trades in einer Gruppe wird nichts interpretiert.
MIN_GRUPPE = 20


def lade_trades(pfad: Path) -> tuple[list[dict], list[dict], list[dict]]:
    """Liest die CSV und trennt sie nach Ereignistyp."""
    with pfad.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter=";"))
    return (
        [r for r in rows if r.get("event") == "OPEN"],
        [r for r in rows if r.get("event") == "CLOSE"],
        [r for r in rows if r.get("event") == "PARTIAL"],
    )


def zahl(row: dict, key: str, default: float = 0.0) -> float:
    """Spalte als Zahl lesen; fehlt sie oder ist sie leer, gilt `default`."""
    try:
        wert = row.get(key)
        return float(wert) if wert not in (None, "") else default
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
def gesamtbild(closes: list[dict]) -> None:
    pnl = [zahl(r, "pnl_sol") for r in closes]
    pct = [zahl(r, "pnl_pct") for r in closes]
    dauer = [zahl(r, "haltedauer_sek") for r in closes]

    gewinne = [p for p in pnl if p > 0]
    verluste = [p for p in pnl if p <= 0]

    tabelle = Table.grid(padding=(0, 3))
    tabelle.add_column(style="grey70")
    tabelle.add_column(style="bold")

    tabelle.add_row("Trades", str(len(closes)))
    farbe = "green" if sum(pnl) > 0 else "red"
    tabelle.add_row("Ergebnis", f"[{farbe}]{sum(pnl):+.4f} SOL[/]")
    tabelle.add_row("Gewinner / Verlierer", f"{len(gewinne)} / {len(verluste)}")
    trefferquote = len(gewinne) / len(closes) * 100 if closes else 0.0
    tabelle.add_row("Trefferquote", f"{trefferquote:.1f} %")

    if gewinne and verluste:
        mittel_gewinn = st.mean([p for p in pct if p > 0])
        mittel_verlust = st.mean([p for p in pct if p <= 0])
        tabelle.add_row("Ø Gewinn / Ø Verlust",
                        f"{mittel_gewinn:+.1f} % / {mittel_verlust:+.1f} %")

        # Ab welcher Trefferquote traegt sich das? Bei Durchschnittsgewinn G
        # und Durchschnittsverlust V gilt: noetige Quote = V / (G + V).
        g, v = st.mean(gewinne), abs(st.mean(verluste))
        noetig = v / (g + v) * 100 if (g + v) > 0 else 0.0
        urteil = "green" if trefferquote >= noetig else "red"
        tabelle.add_row("Noetige Trefferquote fuer ±0",
                        f"[{urteil}]{noetig:.1f} %[/]  "
                        f"(erreicht: {trefferquote:.1f} %)")

    tabelle.add_row("Erwartungswert je Trade",
                    f"{st.mean(pnl) * 1000:+.2f} mSOL"
                    if pnl else "-")
    if dauer:
        tabelle.add_row("Haltedauer Median / Mittel",
                        f"{st.median(dauer):.0f} s / {st.mean(dauer):.0f} s")

    console.print(Panel(tabelle, title="Gesamtbild", border_style="cyan"))


def nach_ausstiegsgrund(closes: list[dict]) -> None:
    tabelle = Table(title="Nach Ausstiegsgrund", title_style="bold")
    tabelle.add_column("Grund")
    tabelle.add_column("Anzahl", justify="right")
    tabelle.add_column("Summe SOL", justify="right")
    tabelle.add_column("Ø %", justify="right")
    tabelle.add_column("Ø Dauer", justify="right")
    tabelle.add_column("Gewinner", justify="right")

    gruppen: dict[str, list[dict]] = defaultdict(list)
    for r in closes:
        gruppen[r.get("grund", "?")].append(r)

    # Schlechtestes zuerst - das ist das, was man reparieren will.
    for grund, rs in sorted(gruppen.items(),
                            key=lambda kv: sum(zahl(r, "pnl_sol") for r in kv[1])):
        summe = sum(zahl(r, "pnl_sol") for r in rs)
        farbe = "green" if summe > 0 else "red"
        gewinner = sum(1 for r in rs if zahl(r, "pnl_sol") > 0)
        tabelle.add_row(
            grund, str(len(rs)),
            f"[{farbe}]{summe:+.4f}[/]",
            f"{st.mean([zahl(r, 'pnl_pct') for r in rs]):+.1f}",
            f"{st.mean([zahl(r, 'haltedauer_sek') for r in rs]):.0f} s",
            f"{gewinner}/{len(rs)}",
        )
    console.print(tabelle)


def nach_haltedauer(closes: list[dict]) -> None:
    grenzen = [(0, 2), (2, 5), (5, 15), (15, 60), (60, float("inf"))]
    tabelle = Table(title="Nach Haltedauer", title_style="bold")
    tabelle.add_column("Dauer")
    tabelle.add_column("Anzahl", justify="right")
    tabelle.add_column("Summe SOL", justify="right")
    tabelle.add_column("Ø %", justify="right")
    tabelle.add_column("Gewinner", justify="right")

    for lo, hi in grenzen:
        rs = [r for r in closes if lo <= zahl(r, "haltedauer_sek") < hi]
        if not rs:
            continue
        summe = sum(zahl(r, "pnl_sol") for r in rs)
        farbe = "green" if summe > 0 else "red"
        name = f"{lo:.0f}-{hi:.0f} s" if hi != float("inf") else f"ueber {lo:.0f} s"
        tabelle.add_row(
            name, str(len(rs)), f"[{farbe}]{summe:+.4f}[/]",
            f"{st.mean([zahl(r, 'pnl_pct') for r in rs]):+.1f}",
            f"{sum(1 for r in rs if zahl(r, 'pnl_sol') > 0)}/{len(rs)}",
        )
    console.print(tabelle)


def nach_einstiegsbedingung(closes: list[dict], opens: list[dict]) -> bool:
    """
    Der eigentlich interessante Teil: Unter welchen Bedingungen hat es
    funktioniert? Gibt False zurueck, wenn die noetigen Spalten fehlen.
    """
    if not closes or "progress_pct" not in closes[0]:
        return False

    # Die Einstiegswerte stehen auf der OPEN-Zeile; ueber die Mint-Adresse
    # lassen sie sich dem passenden CLOSE zuordnen.
    einstieg = {r["mint"]: r for r in opens}

    felder = [
        ("progress_pct", "Curve-Progress beim Kauf", "%",
         [(0, 10), (10, 20), (20, 30), (30, 40), (40, 101)]),
        ("momentum_pct", "Momentum im Fenster", "%",
         [(0, 15), (15, 30), (30, 60), (60, 120), (120, 1e9)]),
        ("kaufdruck_sol", "Kaufdruck im Fenster", "SOL",
         [(0, 2), (2, 4), (4, 8), (8, 1e9)]),
        ("dev_anteil_pct", "Dev-Anteil", "%",
         [(0, 2), (2, 5), (5, 10), (10, 101)]),
    ]

    for feld, titel, einheit, grenzen in felder:
        tabelle = Table(title=titel, title_style="bold")
        tabelle.add_column("Bereich")
        tabelle.add_column("Anzahl", justify="right")
        tabelle.add_column("Summe SOL", justify="right")
        tabelle.add_column("Ø %", justify="right")
        tabelle.add_column("Trefferquote", justify="right")
        tabelle.add_column("", justify="left")

        etwas_gefunden = False
        for lo, hi in grenzen:
            rs = []
            for r in closes:
                quelle = einstieg.get(r.get("mint", ""))
                if quelle is None:
                    continue
                wert = zahl(quelle, feld, default=-1)
                if lo <= wert < hi:
                    rs.append(r)
            if not rs:
                continue
            etwas_gefunden = True
            summe = sum(zahl(r, "pnl_sol") for r in rs)
            gewinner = sum(1 for r in rs if zahl(r, "pnl_sol") > 0)
            farbe = "green" if summe > 0 else "red"
            name = (f"{lo:.0f}-{hi:.0f} {einheit}" if hi < 1e9
                    else f"ueber {lo:.0f} {einheit}")
            hinweis = "" if len(rs) >= MIN_GRUPPE else "[grey50]zu wenige[/]"
            tabelle.add_row(
                name, str(len(rs)), f"[{farbe}]{summe:+.4f}[/]",
                f"{st.mean([zahl(r, 'pnl_pct') for r in rs]):+.1f}",
                f"{gewinner / len(rs) * 100:.0f} %", hinweis,
            )
        if etwas_gefunden:
            console.print(tabelle)

    console.print(
        f"[grey70]Gruppen mit weniger als {MIN_GRUPPE} Trades sind markiert - "
        "aus denen sollte man nichts ableiten.[/]\n")
    return True


def empfehlungen(closes: list[dict], opens: list[dict], hat_spalten: bool) -> None:
    """
    Ableitungen, aber nur wo die Datenmenge sie traegt. Lieber "weiss ich
    nicht" sagen als eine Zahl erfinden.
    """
    zeilen: list[str] = []

    pnl = [zahl(r, "pnl_sol") for r in closes]
    if len(closes) < 50:
        zeilen.append(
            f"[yellow]Nur {len(closes)} Trades.[/] Das reicht fuer keine "
            "Aussage. Lass den Bot laenger laufen - unter ~100 Trades ist "
            "alles Zufall.")

    # Totalverluste
    totale = [r for r in closes if zahl(r, "pnl_pct") <= -95]
    if totale and pnl:
        anteil = sum(zahl(r, "pnl_sol") for r in totale) / sum(pnl) * 100 \
            if sum(pnl) < 0 else 0
        gruende = Counter(r.get("grund") for r in totale)
        zeilen.append(
            f"[red]{len(totale)} Totalverluste[/] ({anteil:.0f} % des "
            f"Verlusts), Gruende: {dict(gruende)}. "
            "Stehen dort viele TIME oder FLIP, pruefe, ob du die Version mit "
            "dem LIQ-Ausstieg laeufst (Kurve leergezogen).")

    # Sekundentrades
    schnell = [r for r in closes if zahl(r, "haltedauer_sek") < 2]
    if len(schnell) >= MIN_GRUPPE:
        summe = sum(zahl(r, "pnl_sol") for r in schnell)
        zeilen.append(
            f"[yellow]{len(schnell)} von {len(closes)} Trades waren nach unter "
            f"2 Sekunden vorbei[/] ({summe:+.4f} SOL). Der Bot kauft und ist "
            "sofort wieder draussen - jedes Mal doppelte Gebuehren. Wenn das "
            "haeufig FLIP ist, ist entweder der Einstieg zu spaet oder "
            "net_sell_flip_threshold_sol zu empfindlich.")

    # Trades, die weit genug gelaufen sind, dass die Strategie greift
    teil_trades = [r for r in closes if zahl(r, "pnl_pct") >= 25]
    if len(teil_trades) >= 5:
        zeilen.append(
            f"[green]{len(teil_trades)} Trades[/] haben es ueber +25 % "
            "geschafft - dort funktioniert die Strategie. Die Frage ist, ob "
            "man die vorher erkennt; dafuer sind die Tabellen oben da.")

    if not hat_spalten:
        zeilen.append(
            "[yellow]Diese trades.csv stammt von einer aelteren Version[/] und "
            "enthaelt die Einstiegswerte (Progress, Kaufdruck, Momentum) noch "
            "nicht. Damit laesst sich nicht sagen, WORAN gute Trades zu "
            "erkennen waren. Der naechste Lauf schreibt sie mit.")

    if not zeilen:
        zeilen.append("Keine auffaelligen Muster gefunden.")

    console.print(Panel("\n\n".join(zeilen), title="Was das heisst",
                        border_style="yellow"))


def main() -> int:
    pfad = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT_ROOT / "trades.csv"

    if not pfad.exists():
        console.print(Panel(
            f"Keine Datei gefunden: {pfad}\n\n"
            "Die trades.csv entsteht, sobald der Bot den ersten Trade "
            "abgeschlossen hat. Lass ihn erst eine Weile laufen.",
            title="Nichts auszuwerten", border_style="red"))
        return 1

    opens, closes, partials = lade_trades(pfad)

    if not closes:
        console.print(Panel(
            f"In {pfad.name} steht noch kein abgeschlossener Trade.",
            title="Nichts auszuwerten", border_style="yellow"))
        return 0

    console.print()
    console.print(f"[bold]Auswertung von {pfad.name}[/]  "
                  f"[grey70]({len(opens)} Kaeufe, {len(closes)} abgeschlossen, "
                  f"{len(partials)} Teilverkaeufe)[/]\n")

    gesamtbild(closes)
    nach_ausstiegsgrund(closes)
    nach_haltedauer(closes)
    hat_spalten = nach_einstiegsbedingung(closes, opens)
    empfehlungen(closes, opens, hat_spalten)

    console.print(
        "[grey70]Denk dran: Einstellungen so lange zu drehen, bis DIESE Datei "
        "gut aussieht, macht den Bot nicht besser - nur angepasster an die "
        "Vergangenheit. Aenderungen immer an einem neuen Lauf pruefen.[/]\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
