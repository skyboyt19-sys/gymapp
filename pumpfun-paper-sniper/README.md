# pump.fun Paper-Sniper

Ein vollautomatischer Sniper-Bot für pump.fun, der **ausschließlich simuliert**.

Der Bot hängt sich an die echten Live-Launches auf pump.fun, liest die echten
Kursdaten von der Blockchain und rechnet Käufe und Verkäufe damit durch — aber
alles nur als Buchung gegen ein **virtuelles SOL-Guthaben**.

---

## Sicherheit: Was dieser Bot nicht kann

Das ist kein Versprechen, sondern im Code festgeschrieben:

| | |
|---|---|
| **Private Key / Seed Phrase** | Wird nie abgefragt, nie gespeichert, nie verwendet. Es gibt keine Funktion, die so etwas entgegennimmt. |
| **Echte Transaktionen** | Unmöglich. Es ist keine Bibliothek installiert, die Transaktionen signieren könnte (kein `solana-py`-Client, keine Keypair-Verwaltung). |
| **Blockchain-Zugriff** | Nur **lesend**. Vor jedem einzelnen RPC-Aufruf prüft `sniper/safety.py`, ob die Methode auf der Erlaubnisliste steht (`getAccountInfo`, `getMultipleAccounts`, …). Alles andere wird blockiert. |
| **Startprüfung** | Findet der Bot beim Start eine Umgebungsvariable, die nach einem Wallet-Geheimnis aussieht (`*PRIVATE_KEY*`, `*SEED_PHRASE*`, `*MNEMONIC*`, …), **startet er gar nicht erst**. |

Dein Geld kann durch diesen Bot nicht bewegt werden, weil er keinen Weg dazu hat.

---

## Teil 1 — Installation unter Windows

### Schritt 1: Python installieren

Nur nötig, falls du Python noch nicht hast.

1. Gehe auf **https://www.python.org/downloads/windows/**
2. Lade **Python 3.11** oder neuer herunter (Button „Download Python 3.x.x").
3. Starte die heruntergeladene Datei.
4. **Wichtig:** Setze auf der ersten Seite unten den Haken bei
   **„Add python.exe to PATH"**. Ohne diesen Haken findet Windows Python später nicht.
5. Dann auf „Install Now" klicken und warten.

**Prüfen, ob es geklappt hat:** Drücke `Windows-Taste + R`, tippe `cmd`, Enter.
Tippe in das schwarze Fenster:

```
python --version
```

Wenn dort `Python 3.11.x` (oder höher) steht, ist alles in Ordnung.

### Schritt 2: Den Bot-Ordner ablegen

Kopiere den Ordner `pumpfun-paper-sniper` an einen Ort ohne Umlaute und
Leerzeichen im Pfad, zum Beispiel:

```
C:\sniper\
```

### Schritt 3: Starten (macht den Rest automatisch)

**Doppelklick auf `run.bat`.**

Beim ersten Start passiert automatisch:

1. Es wird eine abgeschottete Python-Umgebung angelegt (Ordner `.venv`) —
   damit bringt der Bot dein übriges Python nicht durcheinander.
2. Alle benötigten Pakete werden installiert (`pip install -r requirements.txt`).
   Das dauert **1–2 Minuten**, aber nur beim allerersten Mal.
3. Die Datei `.env` wird aus `.env.example` erzeugt.
4. Der Bot startet.

Ab dem zweiten Doppelklick startet er sofort.

> **Falls Windows SmartScreen meckert** („Der Computer wurde geschützt"):
> Klicke auf „Weitere Informationen" → „Trotzdem ausführen". Das ist die
> normale Warnung für jede nicht signierte `.bat`-Datei.

### Schritt 4 (empfohlen): Erst den Feed testen

Bevor du den ganzen Bot laufen lässt, prüfe mit einem Klick, ob die
Live-Verbindung auf deinem PC funktioniert:

**Doppelklick auf `check_feed.bat`**

Es öffnet sich ein Fenster, das **nichts handelt** und nur die neuen
pump.fun-Token auflistet, sobald sie starten:

```
   1  PEPE2      Pepe The Second          Preis 0.0000000280 SOL  Dev-Buy  1.200 SOL  Dev-Anteil   3.8 %
   2  MOONX      Moon Explorer            Preis 0.0000000279 SOL  Dev-Buy  0.500 SOL  Dev-Anteil   1.6 %
```

Läuft das (typischerweise mehrere Token pro Minute), funktioniert alles.
Beenden mit `STRG+C`.

---

## Teil 2 — Der laufende Bot

### Das Dashboard

```
╭──────────────────────────────────────────────────────────────────────────╮
│   pump.fun SNIPER    PAPER-TRADING - reine Simulation. Kein echtes Geld  │
╰──────────────────────────────────────────────────────────────────────────╯
╭─────────────────────────── Konto (virtuell) ─────────────────────────────╮
│ Guthaben (frei)   9.5500 SOL   Gescannt   142   Feed    verbunden (142)  │
│ Gesamtwert        9.8231 SOL   Gesnipet     7   RPC     ok (86 ms)       │
│ P&L gesamt       -0.1769 SOL   Geskippt   135   Trades           5       │
│ Trefferquote        40.0 %     Offen      2/4   Beobachtet       3       │
╰──────────────────────────────────────────────────────────────────────────╯
```

| Feld | Bedeutung |
|---|---|
| **Guthaben (frei)** | Virtuelles SOL, das gerade nicht in Positionen steckt |
| **Gesamtwert** | Guthaben **plus** aktueller Verkaufswert der offenen Positionen |
| **P&L gesamt** | Gewinn/Verlust gegenüber dem Startguthaben |
| **Trefferquote** | Anteil der geschlossenen Trades mit Gewinn |
| **Gescannt** | Wie viele Launches der Bot insgesamt gesehen hat |
| **Geskippt** | Wie viele davon die Einstiegsfilter nicht bestanden haben |
| **Beobachtet** | Token, die gerade im Signalfenster sind (noch nicht gekauft) |

Darunter siehst du die **offenen Positionen** (mit Live-P&L und der Restzeit bis
zum Zwangsverkauf), die **letzten geschlossenen Trades** und die letzten
**Ereignisse**.

Dass „Geskippt" viel größer ist als „Gesnipet", ist normal und gewollt — die
Filter sind streng.

### Ausstiegsgründe in der Trade-Liste

| Kürzel | Bedeutung |
|---|---|
| `TP` | Take-Profit erreicht (+40 %) |
| `PARTIAL` | Teilverkauf bei +25 % (halbe Position) |
| `TRAIL` | Trailing-Stop ausgelöst |
| `SL` | Stop-Loss (−25 %) |
| `RUG` | Kurssturz innerhalb eines einzigen Ticks |
| `FLIP` | Kaufdruck ist in Nettoverkäufe gekippt |
| `TIME` | Harter Zeitstopp nach 120 Sekunden |
| `MIGR` | Token ist zu PumpSwap migriert |
| `SHUTDOWN` | Du hast den Bot beendet (`STRG+C`) |

### Beenden

**`STRG+C`** im Bot-Fenster. Der Bot schließt dann alle offenen
Paper-Positionen, zeigt die Abschluss-Zusammenfassung an und beendet sich sauber.

---

## Teil 3 — Einstellungen ändern (`config.yaml`)

Öffne `config.yaml` mit einem Texteditor (Rechtsklick → „Öffnen mit" → Editor).
Änderungen greifen nach einem **Neustart** des Bots.

**Zwei Regeln:** Nur die Zahl hinter dem Doppelpunkt ändern, und **niemals
Tabulatoren** benutzen — nur Leerzeichen.

### Die wichtigsten Stellschrauben

| Einstellung | Wirkung, wenn du sie **erhöhst** |
|---|---|
| `position_size_sol` | Größerer Einsatz pro Trade → größere Gewinne **und** Verluste |
| `max_open_positions` | Mehr Token gleichzeitig → mehr Streuung, mehr RPC-Last |
| `signal_window_sec` | Der Bot wartet länger ab → sicherere Signale, aber schlechterer Einstiegskurs |
| `min_net_buy_volume_sol` | **Strenger.** Weniger Trades, aber nur bei echtem Kaufdruck |
| `min_price_gain_in_window_pct` | **Strenger.** Nur Token, die schon deutlich anziehen |
| `max_curve_progress_pct` | Lockerer — der Bot kauft auch Token, die schon weiter gelaufen sind |
| `max_dev_holding_pct` | Lockerer — riskanter, weil der Ersteller mehr Token hält |
| `take_profit_pct` | Gewinne laufen lassen, aber häufiger wieder abgeben |
| `stop_loss_pct` | Weiterer Stop → weniger Fehlausstiege, größere Einzelverluste |
| `hard_time_stop_sec` | Längere Haltedauer (**dieser Wert ist die harte Obergrenze**) |
| `rpc_poll_ms` | Seltenere Kursabfragen → schont die RPC, aber träge Reaktion |

### „Ich will weniger / mehr Trades sehen"

* **Mehr Trades:** `min_net_buy_volume_sol` auf `0.5` und
  `min_price_gain_in_window_pct` auf `3` senken.
* **Weniger, dafür bessere:** `min_net_buy_volume_sol` auf `3.0` und
  `min_price_gain_in_window_pct` auf `15` erhöhen.

### Reihenfolge der Ausstiegsregeln

Bei jedem Kurs-Tick wird in genau dieser Reihenfolge geprüft — die erste
zutreffende Regel gewinnt:

```
1. Migriert   →  2. Rug   →  3. Stop-Loss   →  4. (Teil-)Take-Profit
             →  5. Trailing   →  6. Net-Sell-Flip   →  7. Hard-Time-Stop
```

Der **Hard-Time-Stop steht bewusst am Ende**: Er ist das letzte Wort. Egal was
der Kurs macht — nach `hard_time_stop_sec` (Standard 120 s) wird verkauft.

---

## Teil 4 — Schnellere RPC (empfohlen)

Standardmäßig nutzt der Bot die öffentliche Solana-RPC
(`https://api.mainnet-beta.solana.com`). Die funktioniert, ist aber stark
rate-limitiert. Bei mehreren offenen Positionen siehst du dann im Dashboard
`RPC: x Fehler in Folge` und im Log Meldungen über **HTTP 429**.

Ein kostenloser Zugang läuft deutlich stabiler:

1. Kostenlos registrieren bei **https://www.helius.dev/** (oder
   https://www.quicknode.com/).
2. Du bekommst eine URL wie
   `https://mainnet.helius-rpc.com/?api-key=abc123…`
3. Öffne die Datei `.env` im Bot-Ordner mit dem Editor.
4. Ersetze die Zeile durch deine URL:

```
SOLANA_RPC_URL=https://mainnet.helius-rpc.com/?api-key=abc123...
```

5. Bot neu starten.

> Das ist ein reiner **Lese**-Zugang. Auch damit kann der Bot keine Transaktion
> senden. In `.env` gehört **kein** Private Key — der Bot würde den Start
> verweigern.

---

## Teil 5 — Protokolldateien

| Datei | Inhalt |
|---|---|
| `trades.csv` | Jeder Kauf, Teilverkauf und Verkauf mit Preis, P&L und Guthaben. Trennzeichen `;` — **öffnet sich in Excel direkt korrekt** per Doppelklick. |
| `session.log` | Vollständiges Protokoll: Verbindungen, Fehler, jede Entscheidung. Das ist die Datei, in die du bei Problemen schaust. |

Beide Dateien werden fortlaufend erweitert. Zum Zurücksetzen einfach löschen —
der Bot legt sie neu an.

---

## Teil 6 — Fehlersuche

### „Python wurde nicht gefunden"
Bei der Installation der Haken bei **„Add python.exe to PATH"** wurde
vergessen. Python noch einmal installieren, diesmal mit Haken (oder
„Modify" → „Add to PATH").

### Wenn der Feed nicht läuft
Symptom: Im Dashboard steht dauerhaft `Feed: getrennt - Reconnect läuft`,
oder `check_feed.bat` zeigt keinen einzigen Token.

Der Bot versucht dabei **automatisch immer wieder**, sich neu zu verbinden
(mit wachsender Wartezeit bis 30 s) — er stürzt nicht ab. Mögliche Ursachen:

1. **Firewall / Virenscanner** blockiert die WebSocket-Verbindung von Python.
   → Python in der Firewall freigeben.
2. **Firmen- oder Schul-Netzwerk** mit Proxy blockiert WebSockets.
   → Über ein anderes Netz probieren (z. B. Handy-Hotspot).
3. **PumpPortal ist gerade offline.** Prüfe https://pumpportal.fun/ im Browser.

**Alternative Datenquellen** (falls PumpPortal dauerhaft ausfällt): Bitquery
bietet pump.fun-GraphQL-Streams mit kostenlosem Kontingent, erfordert aber eine
Registrierung und einen API-Key. Der Feed ist in `sniper/feed.py` sauber
gekapselt — es müsste nur diese eine Datei ersetzt werden, sie liefert
`NewTokenEvent`-Objekte an den Rest des Bots. Solange PumpPortal läuft, ist es
die einzige wirklich schlüsselfreie Quelle und deshalb der Standard.

### „RPC: x Fehler in Folge"
Die öffentliche RPC drosselt dich. Lösung: kostenlosen Key eintragen
(→ Teil 4) oder `rpc_poll_ms` in der `config.yaml` auf `1500` erhöhen.

### Der Bot snipet gar nichts
Das ist meistens korrektes Verhalten — die Filter sind streng, und viele
Launches sind tot. Schau in `session.log` (bzw. starte mit
`.venv\Scripts\python.exe -m sniper.main --verbose`), dort steht für jeden
übersprungenen Token der Grund, z. B.
`SKIP ABC: Kaufdruck zu klein (0.42 < 1.5 SOL)`. Wenn du dieselbe Begründung
immer wieder siehst, ist das die Stellschraube, die du lockern müsstest.

---

## Teil 7 — Was ich gegenüber deiner Vorlage geprüft und geändert habe

Du hattest darum gebeten, die aktuellen Docs zu prüfen und anzupassen. Ergebnis:

**Bestätigt, unverändert übernommen:**
* Das **Bonding-Curve-Layout** stimmt weiterhin. Discriminator
  `0x17b7f83760d8ac60` und alle Byte-Offsets (`virtualTokenReserves` @ 0x08 bis
  `complete` @ 0x30) entsprechen der offiziellen Doku
  (github.com/pump-fun/pump-public-docs).
* **Preisformel und Curve-Progress** wie von dir angegeben. Die
  Startreserve `793.100.000.000.000` ist weiterhin der Standardwert.
* **PumpPortal** `wss://pumpportal.fun/api/data` mit `subscribeNewToken` ist
  weiterhin kostenlos und ohne Key nutzbar. Der Bot hält, wie vorgeschrieben,
  **genau eine** Verbindung.
* **1 % Gebühr** auf der Bonding Curve ist weiterhin korrekt.

**Angepasst:**
1. **Zusätzliches `creator`-Feld.** Neuere Bonding-Curve-Accounts haben hinter
   `complete` noch eine 32-Byte-Creator-Adresse. Der Bot liest sie, wenn sie da
   ist, und kommt auch mit älteren (kürzeren) Accounts zurecht — sonst wären
   je nach Token-Alter Dekodierfehler möglich.
2. **Pool-Filter.** PumpPortal streamt inzwischen auch Launches anderer
   Launchpads (Feld `pool`, z. B. `"bonk"`). Deren Accounts haben ein anderes
   Layout. Der Bot verarbeitet deshalb nur `pool: "pump"`
   (einstellbar unter `advanced.allowed_pools`).
3. **`getMultipleAccounts` statt `getAccountInfo`.** Du hattest
   `getAccountInfo` genannt. Bei bis zu 4 Positionen plus mehreren beobachteten
   Kandidaten wären das pro Sekunde schnell 10+ Einzelaufrufe — die öffentliche
   RPC blockt das sofort. Der Bot holt jetzt **alle** beobachteten Accounts mit
   *einem* Aufruf (bis zu 100 Stück). Gleiche Daten, ein Bruchteil der Last.
4. **Bewertung migrierter Token.** Ein migrierter Token wird **nicht** als
   Totalverlust gebucht. Migration heißt: die Kurve ist voll, der Kurs steht am
   Hoch, und der Handel läuft auf PumpSwap weiter. Der Bot handelt dort nicht
   mehr (wie von dir gefordert), bewertet den Restbestand beim Schließen aber
   zum zuletzt gesehenen Kurs abzüglich Gebühr und Slippage. Mit 0 zu bewerten
   würde die Trefferquote systematisch verfälschen.
5. **`advanced:`-Block in der `config.yaml`.** Deine Werte sind exakt wie
   vorgegeben übernommen. Darunter kam ein zusätzlicher, kommentierter Block für
   Details, die eine Zahl brauchten, aber in deiner Vorlage offen waren — z. B.
   über welches Zeitfenster der „Net-Sell-Flip" gemessen wird (5 s) und ab
   welchem Abfluss er zählt (0,05 SOL, damit Mini-Verkäufe keinen Fehlalarm
   auslösen). Du musst dort nichts anfassen.

**Nicht live getestet:** Die Umgebung, in der ich den Bot gebaut habe, hat
keinen Netzwerkzugang zu PumpPortal oder zur Solana-RPC. Die Mathematik, die
Strategie-Logik und der komplette Ablauf sind durch **59 automatische Tests**
und einen End-to-End-Durchlauf mit simulierten Kursverläufen abgedeckt (alle
Ausstiegswege — TP, Teil-TP, SL, Trailing, Rug, Flip, Time-Stop, Migration —
laufen darin durch). Die echte Verbindung musst du einmal mit
`check_feed.bat` auf deinem PC bestätigen.

---

## Teil 8 — Ehrliche Grenzen dieser Simulation

Damit du die Ergebnisse richtig einordnest:

* **Der Bot ist kein echter Sniper.** Echte Sniper landen in derselben
  Solana-Transaktion oder demselben Block wie der Dev-Buy. Dieser Bot schaut
  erst 10 Sekunden zu (`signal_window_sec`) — das ist bewusst so, weil ohne
  eigenen Node und ohne bezahlten Stream ein Block-0-Einstieg gar nicht
  möglich wäre. Die Ergebnisse sind daher die einer *Momentum*-Strategie,
  nicht die eines Block-0-Snipes.
* **Kursauflösung.** Der Kurs wird alle `rpc_poll_ms` (800 ms) abgefragt.
  Was zwischen zwei Abfragen passiert, sieht der Bot nicht. Ein Rug, der
  innerhalb von 200 ms durchläuft, wird erst beim nächsten Tick erkannt — in
  der Realität wärst du dann schlechter raus als hier simuliert.
* **Kein Einfluss auf den Markt.** Der simulierte Kauf verändert die echte
  Kurve nicht. Bei `position_size_sol: 0.15` ist das vernachlässigbar; bei
  großen Einsätzen wäre die Simulation zu optimistisch.
* **Slippage ist eine Annahme.** Die 3 % sind ein Pauschalwert. Real
  konkurrierst du mit anderen Bots um denselben Block; das kann deutlich
  schlechter ausfallen.
* **Keine fehlgeschlagenen Transaktionen.** In der Realität scheitert ein Teil
  der Käufe (zu wenig Priority Fee, Slippage-Limit überschritten) und kostet
  trotzdem Gebühren. Das simuliert der Bot nicht.

Kurz: Die Zahlen sind **eher besser als die Realität**. Behandle sie als Test
der Strategie-Logik, nicht als Renditeversprechen.

---

## Projektstruktur

```
pumpfun-paper-sniper/
├── run.bat              ← Doppelklick zum Starten
├── check_feed.bat       ← Doppelklick für den Feed-Test
├── config.yaml          ← alle Einstellungen (kommentiert)
├── .env.example         ← Vorlage für die RPC-URL
├── requirements.txt     ← benötigte Pakete
│
├── sniper/
│   ├── safety.py        ← Sicherheitsnetz: nur lesende Zugriffe
│   ├── config.py        ← liest und prüft config.yaml + .env
│   ├── curve.py         ← Bonding Curve: dekodieren, Preis, Fill-Simulation
│   ├── feed.py          ← PumpPortal-WebSocket (neue Launches)
│   ├── rpc.py           ← lesender Solana-RPC-Client
│   ├── strategy.py      ← Einstiegsfilter und Ausstiegsregeln
│   ├── paper_engine.py  ← virtuelles Konto und Buchhaltung
│   ├── market.py        ← Herzschlag-Schleife, verbindet alles
│   ├── dashboard.py     ← Live-Anzeige in der Konsole
│   └── main.py          ← Start, Abschaltung, Zusammenfassung
│
└── tests/               ← 59 automatische Tests
```

### Tests ausführen (optional)

```
.venv\Scripts\python.exe -m pytest -q
```

Erwartete Ausgabe: `59 passed`.
