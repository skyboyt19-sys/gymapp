# pump.fun Sniper-Bot

Ein automatischer Sniper-Bot für pump.fun mit **zwei Betriebsarten**:

| | |
|---|---|
| **Simulation** (Standard) | Hängt sich an die echten Live-Launches, rechnet Käufe und Verkäufe gegen die echten Kursdaten — aber nur gegen ein virtuelles Guthaben. Kostet nichts. |
| **Echtgeld** | Dieselbe Strategie, aber die Käufe und Verkäufe gehen wirklich raus, über eine Bot-Wallet bei PumpPortal. |

Umgeschaltet wird mit **einer Zeile** in der `config.yaml`:

```yaml
live_trading: false     # false = Simulation, true = echtes Geld
```

---

## Sicherheit

| | |
|---|---|
| **Private Key / Seed Phrase** | Wird **nie** abgefragt, nie gespeichert, nie verwendet — auch im Echtgeld-Modus nicht. Der Bot signiert grundsätzlich nichts selbst; das macht PumpPortal mit deinem API-Key. |
| **Startprüfung** | Findet der Bot in der Umgebung eine Variable, die nach einem Wallet-Geheimnis aussieht (`*PRIVATE_KEY*`, `*SEED_PHRASE*`, `*MNEMONIC*` …), **startet er gar nicht erst**. |
| **Blockchain-Zugriff** | Nur **lesend**. Vor jedem RPC-Aufruf prüft `sniper/safety.py`, ob die Methode auf der Erlaubnisliste steht. `sendTransaction` und Verwandte sind dauerhaft gesperrt. |
| **Reichweite** | Der Bot kann ausschließlich bewegen, was auf der **Bot-Wallet** liegt. Deine Haupt-Wallet ist für ihn nicht erreichbar. |
| **Not-Aus** | Verliert die Bot-Wallet 30 % (einstellbar), verkauft der Bot alles und schaltet sich ab. |

Der **API-Key ist trotzdem geheim** — wer ihn hat, kann über deine Bot-Wallet handeln. Behandle ihn wie ein Passwort und lade nur so viel auf die Wallet, wie du bereit bist zu verlieren.

---

# Teil 1 — Installation unter Windows

### Schritt 1: Python installieren

Nur nötig, falls noch nicht vorhanden.

1. **https://www.python.org/downloads/windows/** → Python 3.11 oder neuer laden
2. Installer starten
3. **Wichtig:** Haken bei **„Add python.exe to PATH"** setzen
4. „Install Now"

### Schritt 2: Ordner ablegen

Den Ordner an einen Ort **ohne Umlaute und Leerzeichen** kopieren, z. B. `C:\sniper\`

### Schritt 3: Starten

**Doppelklick auf `run.bat`.** Beim ersten Start legt es automatisch die Python-Umgebung an, installiert die Pakete (1–2 Minuten) und erzeugt die `.env`. Danach startet er sofort.

> Windows SmartScreen: „Weitere Informationen" → „Trotzdem ausführen".

### Schritt 4: Feed testen

**Doppelklick auf `check_feed.bat`** — listet nur die neuen Launches auf, handelt nichts. Kommen dort Token an, funktioniert alles. Beenden mit `STRG+C`.

---

# Teil 2 — Simulation (fang hier an)

Standardmäßig läuft der Bot simuliert. Das Dashboard zeigt:

- virtuelles Guthaben, Gesamtwert, P&L, Trefferquote
- Zähler: gescannt / gesnipet / geskippt
- offene Positionen mit Live-P&L und Restzeit bis zum Zwangsverkauf
- die letzten geschlossenen Trades

**Ausstiegsgründe:**

| Kürzel | Bedeutung |
|---|---|
| `TP` | Take-Profit (+40 %) |
| `PARTIAL` | Teilverkauf bei +25 % (halbe Position) |
| `TRAIL` | Trailing-Stop |
| `SL` | Stop-Loss (−25 %) |
| `RUG` | Kurssturz in einem einzigen Tick |
| `LIQ` | Kurve leergezogen — der Kurs steht, aber es ist kein SOL mehr da, das ausgezahlt werden könnte |
| `FLIP` | Kaufdruck in Nettoverkäufe gekippt |
| `TIME` | Harter Zeitstopp (120 s) |
| `MIGR` | Token zu PumpSwap migriert |
| `SHUTDOWN` | Du hast beendet |

Beenden mit **STRG+C**. Alle Trades landen in `trades.csv` (öffnet sich per Doppelklick direkt in Excel).

**Lass das ein paar Stunden laufen, bevor du auf Echtgeld umschaltest.** Wenn die Strategie simuliert Verluste macht, macht sie mit echtem Geld dieselben Verluste — nur teurer.

---

# Teil 3 — Echtgeld-Modus einschalten

## Schritt 1: Bot-Wallet bei PumpPortal anlegen

1. Auf **https://pumpportal.fun/** gehen
2. Zu **„Lightning Transaction API"**
3. Dort eine Wallet erstellen lassen. Du bekommst zwei Dinge:
   - einen **API-Key** (geheim)
   - eine **Wallet-Adresse** (öffentlich, fängt meist mit einem Buchstaben/Zahl an, 32–44 Zeichen)
4. **Beide sofort sichern**, z. B. in einer Textdatei. Den API-Key bekommst du unter Umständen kein zweites Mal zu sehen.

> Diese Wallet gehört zu deinem API-Key. Sie ist getrennt von deiner normalen Phantom-Wallet — genau das ist der Sinn.

## Schritt 2: SOL auf die Bot-Wallet schicken

Von deiner Börse oder deiner Haupt-Wallet an die **Wallet-Adresse** aus Schritt 1.

**Wie viel?** Bei den Standardeinstellungen (0,15 SOL Einsatz, 4 Positionen gleichzeitig):

```
4 × 0,15 SOL   = 0,60 SOL   für die Positionen
+ ca. 0,10 SOL             Gebührenreserve
--------------------------------
≈ 0,70 SOL
```

Willst du mit weniger anfangen, setz in der `config.yaml` `max_open_positions: 2` — dann reichen ~0,35 SOL.

## Schritt 3: Zugangsdaten eintragen

Datei **`.env`** im Bot-Ordner mit dem Editor öffnen (Rechtsklick → Öffnen mit → Editor) und die beiden Zeilen ausfüllen:

```
PUMPPORTAL_API_KEY=dein-api-key-hier
BOT_WALLET_PUBKEY=deine-wallet-adresse-hier
```

> Falls es keine `.env` gibt: einmal `run.bat` starten, dann wird sie angelegt.
> In diese Datei gehört **niemals ein Private Key**.

## Schritt 4: Umschalten

Datei **`config.yaml`** öffnen, ganz oben:

```yaml
live_trading: true
```

Speichern.

## Schritt 5: Starten

**Doppelklick auf `run.bat`.**

Jetzt kommt ein **roter Warnbildschirm** mit deiner Wallet-Adresse, dem aktuellen Guthaben, dem Einsatz pro Trade und der Not-Aus-Schwelle — plus ein **Countdown von 8 Sekunden**. In dieser Zeit kannst du mit `STRG+C` noch abbrechen.

Danach handelt der Bot mit echtem Geld. Das Dashboard ist rot statt grün, damit du die Betriebsart nie verwechselst.

## Schritt 6: Beenden

**STRG+C** — und dann **das Fenster offen lassen**, bis „Abschluss der Sitzung" erscheint. Der Bot verkauft dabei alle offenen Positionen. Das dauert ein paar Sekunden pro Position.

> Wenn du den PC einfach ausschaltest oder das Fenster wegklickst, bleiben die Token auf der Bot-Wallet liegen. Dafür gibt es Teil 4.

---

# Teil 4 — Notverkauf

**Doppelklick auf `panic_sell.bat`**

Das Skript listet alle Token auf, die auf der Bot-Wallet liegen, fragt einmal nach (du musst `JA` tippen) und verkauft dann alles zu 100 %.

Brauchst du, wenn:
- der Bot abgestürzt ist oder der PC ausgegangen ist
- ein Verkauf endgültig fehlgeschlagen ist
- du einfach schnell alles glattstellen willst

**Warum es dieses Skript geben muss:** Die Bot-Wallet bei PumpPortal ist eine reine API-Wallet. Du kannst sie nicht im Browser mit pump.fun verbinden und dort von Hand verkaufen. Ohne dieses Skript kämst du an hängengebliebene Token nicht heran.

---

# Teil 4b — Auswertung

**Doppelklick auf `auswertung.bat`**

Liest die `trades.csv` und zeigt, woran es liegt: Gesamtergebnis, welche
Trefferquote die Strategie überhaupt bräuchte, welcher Ausstiegsgrund das
meiste Geld kostet — und, sofern die Daten aus einer aktuellen Version stammen,
unter welchen **Einstiegsbedingungen** es funktioniert hat (Curve-Progress,
Momentum, Kaufdruck, Dev-Anteil).

Kann jederzeit laufen, auch während der Bot in einem anderen Fenster arbeitet.

**Wichtig beim Benutzen:** Die Versuchung ist groß, jetzt so lange an den
Filtern zu drehen, bis diese eine Datei ein Plus zeigt. Das ist kein besserer
Bot, sondern nur einer, der die Vergangenheit auswendig gelernt hat — live
verliert er danach genauso. Deshalb:

* Nur Gruppen mit mindestens ~20 Trades ernst nehmen (das Skript markiert zu
  kleine).
* Nur deutliche Unterschiede übernehmen, nicht jede kleine Abweichung.
* Nach jeder Änderung einen **neuen** Lauf abwarten und dort prüfen, ob der
  Effekt bleibt. Nur das zählt.

---

# Teil 4c — Dauerbetrieb: muss der PC anbleiben?

**Ja.** Der Bot braucht durchgehend Internet — er hängt am Live-Feed und fragt
jede 0,8 Sekunden Kurse von der Blockchain ab. Offline gibt es nichts zu
handeln.

Der **Bildschirm darf aber aus sein**. Nur schlafen legen darf sich der
Rechner nicht.

### Das erledigt der Bot selbst

Solange er läuft, sagt er Windows „bitte nicht einschlafen" (Einstellung
`advanced.prevent_sleep`, standardmäßig an). Beim Beenden gibt er die Sperre
wieder frei.

**Warum das wichtig ist:** Geht der PC in den Ruhezustand, hält der Bot an.
Im Echtgeld-Modus liegen die offenen Positionen dann ohne Stop-Loss, ohne
Trailing und ohne Zeitstopp auf der Wallet — bis du den Rechner wieder
aufweckst. Ein Token kann in der Zeit auf null gehen, ohne dass irgendetwas
reagiert.

### Was der Bot nicht verhindern kann

* **Zugeklapptes Notebook** — löst je nach Einstellung trotzdem den
  Ruhezustand aus. Unter *Einstellungen → System → Netzbetrieb und
  Energiesparen → Bildschirm und Ruhezustand* auf „Nie" stellen, und bei
  Notebooks zusätzlich in der Systemsteuerung *„Auswählen, was beim Zuklappen
  des Deckels geschehen soll" → „Nichts tun"*.
* **Stromausfall, Windows-Update, Absturz.** Passiert im Echtgeld-Modus:
  danach `panic_sell.bat` starten, um liegengebliebene Token loszuwerden.

### Wirklich 24/7 ohne eigenen PC

Dafür bräuchtest du einen kleinen Server (VPS) für etwa 4–6 € im Monat, der
durchläuft. Der Bot ist reines Python und läuft auf Linux genauso — die
`.bat`-Dateien sind nur die Windows-Startknöpfe.

Ehrlich gesagt ist das aber ein deutlicher Sprung: Du arbeitest dort über eine
Kommandozeile, ohne Explorer und ohne Doppelklick. Solange du in der
Simulation Daten sammelst, tut es dein PC genauso gut.

---

# Teil 5 — Einstellungen (`config.yaml`)

Mit einem Texteditor öffnen. **Nur die Zahl hinter dem Doppelpunkt ändern, niemals Tabulatoren benutzen.** Änderungen greifen nach einem Neustart.

### Die wichtigsten Werte

| Einstellung | Wirkung, wenn du sie **erhöhst** |
|---|---|
| `position_size_sol` | Größerer Einsatz → größere Gewinne **und** Verluste |
| `max_open_positions` | Mehr Token gleichzeitig → mehr Streuung, mehr Kapitalbedarf |
| `signal_window_sec` | Bot wartet länger ab → sicherere Signale, schlechterer Einstiegskurs |
| `min_net_buy_volume_sol` | **Strenger.** Weniger Trades, nur bei echtem Kaufdruck |
| `min_price_gain_in_window_pct` | **Strenger.** Nur Token, die schon deutlich anziehen |
| `max_curve_progress_pct` | Lockerer — kauft auch später gelaufene Token |
| `take_profit_pct` | Gewinne laufen lassen, aber häufiger wieder abgeben |
| `stop_loss_pct` | Weiterer Stop → weniger Fehlausstiege, größere Einzelverluste |
| `hard_time_stop_sec` | Längere Haltedauer (**harte Obergrenze**) |

### Nur im Echtgeld-Modus (`live:`-Block)

| Einstellung | Bedeutung |
|---|---|
| `max_total_loss_pct: 30` | Not-Aus. Bei 30 % Verlust vom Startkapital: alles verkaufen, abschalten. `0` schaltet ihn aus (nicht empfohlen). |
| `order_slippage_pct: 15` | Wie viel schlechter der Kurs sein darf, bevor die Transaktion abgelehnt wird. Zu niedrig = viele Fehlschläge (kosten trotzdem Gebühren), zu hoch = schlechte Fills. |
| `priority_fee_sol: 0.0005` | Höher = deine Transaktion kommt schneller in einen Block. Bei kleinen Positionen der größte Kostenblock. |
| `min_wallet_balance_sol: 0.02` | Es wird nicht gekauft, wenn danach weniger übrig bliebe. Ohne diese Reserve kämst du aus deinen Positionen nicht mehr raus. |
| `startup_countdown_sec: 8` | Bedenkzeit vor dem ersten echten Trade. |

### Reihenfolge der Ausstiegsregeln

```
1. Migriert  →  2. Liquidität weg  →  3. Rug  →  4. Stop-Loss
            →  5. (Teil-)Take-Profit  →  6. Trailing
            →  7. Net-Sell-Flip  →  8. Hard-Time-Stop
```

Der **Hard-Time-Stop steht bewusst am Ende** — er ist das letzte Wort. Egal was der Kurs macht, nach 120 s wird verkauft.

---

# Teil 6 — Was dich das kostet

Pro Runde (Kauf + Verkauf) fallen an:

| Posten | Kosten |
|---|---|
| pump.fun-Gebühr | 1 % × 2 = **2 %** |
| PumpPortal-Gebühr | 0,5 % × 2 = **1 %** |
| Slippage | mehrere % |
| Priority Fee | ~0,0005 SOL × 2 — **fix, unabhängig von der Größe** |
| Solana-Grundgebühr | ~0,00001 SOL — vernachlässigbar |

Die prozentualen Posten (~3 % plus Slippage) tun bei jeder Größe gleich weh. Der **fixe** Anteil ist bei kleinen Positionen der Killer:

| Einsatz | Fixkosten-Anteil | Gesamtkosten pro Runde |
|---|---|---|
| 0,001 SOL | 100 % + | sinnlos |
| 0,01 SOL | ~20 % | ~29 % |
| 0,05 SOL | ~4 % | ~13 % |
| **0,15 SOL** | ~1,3 % | **~10 %** |

Deshalb steht `take_profit_pct` auf 40: darunter lohnt sich der Trade nicht. Und deshalb sagt ein Test mit Cent-Beträgen nichts über die Strategie aus — er misst nur Gebühren.

**Dazu kommt:** Fehlgeschlagene Transaktionen kosten die Priority Fee trotzdem. Bei engem `order_slippage_pct` kann das ein spürbarer Anteil sein.

---

# Teil 7 — Schnellere RPC (empfohlen)

Standard ist die öffentliche Solana-RPC. Die funktioniert, ist aber stark rate-limitiert — im Dashboard siehst du dann `RPC: x Fehler in Folge`.

Im Echtgeld-Modus ist das **nicht nur unbequem**: Der Bot braucht die RPC, um Fills zu bestätigen und den Not-Aus zu prüfen. Nimm hier einen eigenen Zugang.

1. Kostenlos registrieren bei **https://www.helius.dev/** oder **https://www.quicknode.com/**
2. Du bekommst eine URL wie `https://mainnet.helius-rpc.com/?api-key=abc123…`
3. In der `.env` eintragen:

```
SOLANA_RPC_URL=https://mainnet.helius-rpc.com/?api-key=abc123...
```

Auch das bleibt ein reiner **Lese**-Zugang.

---

# Teil 8 — Protokolldateien

| Datei | Inhalt |
|---|---|
| `trades.csv` | Jeder Kauf, Teilverkauf und Verkauf mit Preis, P&L und Guthaben. Trennzeichen `;` — öffnet in Excel direkt korrekt. |
| `session.log` | Vollständiges Protokoll inklusive aller Transaktions-Signaturen. Bei Problemen die erste Anlaufstelle. |

Jede echte Transaktion wird mit ihrem Solscan-Link geloggt — damit kannst du jeden einzelnen Trade auf der Blockchain nachprüfen.

---

# Teil 9 — Fehlersuche

### „Python wurde nicht gefunden"
Der Haken bei „Add python.exe to PATH" fehlte. Python neu installieren (oder „Modify" → „Add to PATH").

### Feed verbindet nicht
Im Dashboard steht dauerhaft `Feed: getrennt`. Der Bot versucht es automatisch immer wieder (Backoff bis 30 s), er stürzt nicht ab. Ursachen:
1. Firewall/Virenscanner blockiert Python → freigeben
2. Firmen-/Schulnetz mit Proxy → anderes Netz probieren
3. PumpPortal offline → https://pumpportal.fun/ im Browser prüfen

### „RPC: x Fehler in Folge"
Die öffentliche RPC drosselt. → Teil 7, oder `rpc_poll_ms` auf `1500` erhöhen.

### Der Bot snipet nichts
Meist korrekt — die Filter sind streng. Starte mit `--verbose` bzw. schau in `session.log`: dort steht für jeden übersprungenen Token der Grund, z. B. `SKIP ABC: Kaufdruck zu klein (0.42 < 1.5 SOL)`. Siehst du immer dieselbe Begründung, ist das die Stellschraube.

### „Kauf ist NICHT durchgegangen"
Normal beim Sniping. Die Transaktion hat es nicht rechtzeitig in einen Block geschafft oder das Slippage-Limit wurde gerissen. Der Bot bucht nichts und macht weiter. Häuft es sich: `priority_fee_sol` erhöhen (z. B. `0.001`) oder `order_slippage_pct` hochsetzen.

### Der Start bricht mit „Kontostand konnte nicht abgefragt werden" ab
Gewollt. Ohne Kontostand könnte der Bot weder Fills prüfen noch den Not-Aus auslösen — dann handelt er lieber gar nicht. Prüfe `BOT_WALLET_PUBKEY` und die RPC-URL.

---

# Teil 10 — Was ich geprüft und angepasst habe

**Bestätigt (Stand August 2026):**
* Bonding-Curve-Layout unverändert: Discriminator `0x17b7f83760d8ac60`, Offsets `virtualTokenReserves` @ 0x08 bis `complete` @ 0x30 — geprüft gegen github.com/pump-fun/pump-public-docs.
* `subscribeNewToken` bei PumpPortal ist **weiterhin kostenlos und ohne Key**. Kostenpflichtig sind seit Mai 2026 nur die Per-Token-Trade-Streams (`subscribeTokenTrade`, `subscribeAccountTrade`) — die nutzt der Bot bewusst nicht.
* 1 % pump.fun-Gebühr auf der Bonding Curve, 0,5 % PumpPortal-Gebühr pro Trade.

**Angepasst:**
1. **`creator`-Feld:** Neuere Curve-Accounts haben hinter `complete` 32 zusätzliche Bytes. Wird optional gelesen, ältere Accounts funktionieren weiter.
2. **Pool-Filter:** PumpPortal streamt auch andere Launchpads (`pool: "bonk"` etc.) mit anderem Account-Layout. Der Bot verarbeitet nur `pool: "pump"`.
3. **`getMultipleAccounts` statt `getAccountInfo`:** Alle beobachteten Kurse in einem Aufruf statt 10+ Einzelaufrufen pro Sekunde — sonst blockt jede kostenlose RPC sofort.
4. **Migrierte Token nicht als Totalverlust:** Migration heißt volle Kurve und Höchstkurs. Der Bot handelt dort nicht weiter, bewertet den Rest aber zum letzten Kurs.
5. **Beträge aus der Transaktion, nicht aus Kontoständen:** Der erste Entwurf hat den SOL-Aufwand aus der Differenz des Wallet-Guthabens vorher/nachher berechnet. Das ist falsch, sobald mehrere Aufträge gleichzeitig laufen — dann mischt sich der Erlös eines Verkaufs in die Messung eines Kaufs. Ein Testlauf zeigte dadurch `+226 %` statt der echten `+29 %`. Der Bot liest die Beträge jetzt per `getTransaction` direkt aus der jeweiligen Transaktion. Die liefert nebenbei die einzige verlässliche Antwort auf „hat es geklappt?".
6. **Notverkauf-Skript:** Weil die PumpPortal-Wallet eine API-Wallet ist und sich nicht im Browser mit pump.fun verbinden lässt, gäbe es sonst keinen Weg an hängengebliebene Token.

**Nicht live getestet:** Die Umgebung, in der der Bot gebaut wurde, hat keinen Netzzugang zu PumpPortal oder zur Solana-RPC. Abgedeckt sind **73 automatische Tests** plus zwei End-to-End-Durchläufe (Simulation und Echtgeld-Pfad) gegen eine simulierte Wallet und Blockchain — inklusive fehlgeschlagener Aufträge, paralleler Orders, Not-Aus und aller Ausstiegswege. Die echten Verbindungen musst du auf deinem PC bestätigen: erst `check_feed.bat`, dann Simulation, dann Echtgeld.

---

# Teil 11 — Ehrliche Grenzen

* **Der Bot ist kein echter Sniper.** Echte Sniper landen im selben Block wie der Dev-Buy. Dieser Bot schaut erst 10 Sekunden zu — ohne eigenen Node und bezahlten Stream geht es nicht anders. Das ist eine *Momentum*-Strategie, kein Block-0-Snipe.
* **Kursauflösung 800 ms.** Was dazwischen passiert, sieht der Bot nicht. Ein Rug in 200 ms wird zu spät erkannt.
* **Slippage ist eine Annahme** (in der Simulation 3 %). Real konkurrierst du mit anderen Bots um denselben Block; es kann deutlich schlechter laufen.
* **Die Simulation kennt keine fehlgeschlagenen Transaktionen.** Real scheitert ein Teil der Käufe und kostet trotzdem Gebühren. Die simulierten Zahlen sind daher **besser als die Realität**.
* **Memecoin-Sniping ist ein Negativsummenspiel.** Gebühren, Slippage und schnellere Bots ziehen kontinuierlich Wert ab. Die meisten dieser Token gehen auf null. Behandle das als bezahltes Lernexperiment, nicht als Einkommensquelle.

---

## Projektstruktur

```
pumpfun-paper-sniper/
├── run.bat              ← Bot starten
├── check_feed.bat       ← nur den Feed testen
├── panic_sell.bat       ← Notverkauf: alles glattstellen
├── auswertung.bat       ← trades.csv auswerten
├── config.yaml          ← alle Einstellungen
├── .env.example         ← Vorlage für RPC-URL und API-Key
│
├── sniper/
│   ├── safety.py           ← Sperren: keine Keys, nur lesende RPC-Aufrufe
│   ├── config.py           ← liest und prüft config.yaml + .env
│   ├── curve.py            ← Bonding Curve: dekodieren, Preis, Fill-Rechnung
│   ├── feed.py             ← PumpPortal-WebSocket (neue Launches)
│   ├── rpc.py              ← lesender Solana-Client (Kurse, Kontostände, Tx)
│   ├── strategy.py         ← Einstiegsfilter und Ausstiegsregeln
│   ├── paper_engine.py     ← Simulation: virtuelles Konto
│   ├── live_engine.py      ← ECHTGELD: echte Aufträge + Not-Aus
│   ├── pumpportal_trade.py ← einziges Modul, das echtes Geld bewegt
│   ├── market.py           ← Herzschlag-Schleife
│   ├── dashboard.py        ← Live-Anzeige
│   └── main.py             ← Start, Abschaltung, Zusammenfassung
│
└── tests/                  ← 73 automatische Tests
```

### Tests ausführen

```
.venv\Scripts\python.exe -m pytest -q
```

Erwartet: `73 passed`.

### Simulation erzwingen

Auch wenn `live_trading: true` in der Config steht:

```
.venv\Scripts\python.exe -m sniper.main --paper
```
