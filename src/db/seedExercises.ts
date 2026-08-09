import type { Category, Exercise, MuscleGroup } from './types'

/** [Name, primäre Muskelgruppe, sekundäre Gruppen, Kategorie, Kurzanleitung, zeitbasiert?, Pause(s)?] */
type Seed = [string, MuscleGroup, MuscleGroup[], Category, string, boolean?, number?]

const S: Seed[] = [
  // ── Brust ────────────────────────────────────────────────────────────────
  ['Bankdrücken (Langhantel)', 'Brust', ['Trizeps', 'Schultern'], 'Langhantel', 'Schulterblätter zusammenziehen, Stange kontrolliert zur unteren Brust senken, Ellbogen ca. 45° zum Körper.', false, 180],
  ['Schrägbankdrücken (Langhantel)', 'Brust', ['Schultern', 'Trizeps'], 'Langhantel', 'Bank auf 30–45°. Stange zum oberen Brustbereich senken, Rücken bleibt fest an der Bank.', false, 180],
  ['Negativbankdrücken (Langhantel)', 'Brust', ['Trizeps'], 'Langhantel', 'Bank leicht negativ. Stange zur unteren Brust führen, betont die untere Brustpartie.', false, 180],
  ['Bankdrücken (Kurzhantel)', 'Brust', ['Trizeps', 'Schultern'], 'Kurzhantel', 'Hanteln auf Brusthöhe absenken, im Bogen nach oben drücken, oben nicht ganz durchstrecken.'],
  ['Schrägbankdrücken (Kurzhantel)', 'Brust', ['Schultern', 'Trizeps'], 'Kurzhantel', 'Bank 30°. Tiefe Dehnung zulassen, Handgelenke bleiben über den Ellbogen.'],
  ['Negativbankdrücken (Kurzhantel)', 'Brust', ['Trizeps'], 'Kurzhantel', 'Leicht negative Bank, Hanteln kontrolliert zur unteren Brust.'],
  ['Kurzhantel-Fliegende', 'Brust', [], 'Kurzhantel', 'Leicht gebeugte Ellbogen fixieren, Arme im weiten Bogen öffnen und schließen. Kein Drücken.', false, 90],
  ['Schrägbank-Fliegende (Kurzhantel)', 'Brust', ['Schultern'], 'Kurzhantel', 'Auf 30°-Bank, weiter Bogen, Dehnung in der oberen Brust spüren.', false, 90],
  ['Kabelzug-Fliegende (hoch)', 'Brust', [], 'Kabel', 'Züge oben einhängen, Hände vor dem Bauch zusammenführen. Betont die untere Brust.', false, 90],
  ['Kabelzug-Fliegende (tief)', 'Brust', ['Schultern'], 'Kabel', 'Züge unten einhängen, Hände auf Schulterhöhe zusammenführen. Betont die obere Brust.', false, 90],
  ['Butterfly (Maschine)', 'Brust', [], 'Maschine', 'Ellbogen auf Brusthöhe, Griffe langsam zusammenführen und die Spannung 1 Sek. halten.', false, 90],
  ['Brustpresse (Maschine)', 'Brust', ['Trizeps', 'Schultern'], 'Maschine', 'Sitzhöhe so wählen, dass die Griffe auf Brusthöhe liegen. Kontrolliert drücken.'],
  ['Liegestütze', 'Brust', ['Trizeps', 'Schultern', 'Bauch'], 'Körpergewicht', 'Körper bildet eine Linie, Ellbogen ca. 45°, Brust bis knapp über den Boden senken.', false, 90],
  ['Liegestütze erhöht (Füße hoch)', 'Brust', ['Schultern', 'Trizeps'], 'Körpergewicht', 'Füße auf Bank ablegen — mehr Last auf der oberen Brust.', false, 90],
  ['Diamant-Liegestütze', 'Trizeps', ['Brust'], 'Körpergewicht', 'Hände bilden ein Dreieck unter der Brust, Ellbogen eng am Körper.', false, 90],
  ['Dips (Brust-Variante)', 'Brust', ['Trizeps', 'Schultern'], 'Körpergewicht', 'Oberkörper leicht nach vorn neigen, tief absenken bis zur Dehnung in der Brust.', false, 150],
  ['Überzüge (Kurzhantel-Pullover)', 'Brust', ['Rücken', 'Trizeps'], 'Kurzhantel', 'Quer auf der Bank, Hantel im Bogen hinter den Kopf senken, Brustkorb weit öffnen.', false, 90],
  ['Bankdrücken (Smith-Maschine)', 'Brust', ['Trizeps', 'Schultern'], 'Maschine', 'Geführte Stange, ideal ohne Trainingspartner. Zur unteren Brust senken.', false, 150],

  // ── Rücken ───────────────────────────────────────────────────────────────
  ['Klimmzüge (Obergriff)', 'Rücken', ['Bizeps', 'Unterarme'], 'Körpergewicht', 'Schulterbreit+ greifen, Brust zur Stange ziehen, unten voll aushängen.', false, 150],
  ['Klimmzüge (Untergriff)', 'Rücken', ['Bizeps'], 'Körpergewicht', 'Untergriff schulterbreit, Ellbogen nach unten ziehen. Stärkerer Bizeps-Anteil.', false, 150],
  ['Klimmzüge (neutraler Griff)', 'Rücken', ['Bizeps'], 'Körpergewicht', 'Parallelgriff — schulterschonend, starker Latzug.', false, 150],
  ['Latzug (breit)', 'Rücken', ['Bizeps'], 'Kabel', 'Brust raus, Stange zur oberen Brust ziehen, Schulterblätter nach unten-hinten.', false, 120],
  ['Latzug (eng, neutral)', 'Rücken', ['Bizeps'], 'Kabel', 'Parallelgriff, Ellbogen eng am Körper nach unten ziehen.', false, 120],
  ['Latzug (Untergriff)', 'Rücken', ['Bizeps'], 'Kabel', 'Untergriff schulterbreit, betont den unteren Lat und den Bizeps.', false, 120],
  ['Langhantelrudern (vorgebeugt)', 'Rücken', ['Bizeps', 'Hamstrings'], 'Langhantel', 'Hüfte beugen bis ~45°, Rücken gerade, Stange zum Bauchnabel ziehen.', false, 150],
  ['Langhantelrudern (Untergriff)', 'Rücken', ['Bizeps'], 'Langhantel', 'Untergriff, Stange zur unteren Bauchdecke — mehr unterer Lat.', false, 150],
  ['Pendlay Row', 'Rücken', ['Bizeps'], 'Langhantel', 'Oberkörper parallel zum Boden, Stange bei jeder Wdh. am Boden ablegen, explosiv ziehen.', false, 150],
  ['Kurzhantelrudern (einarmig)', 'Rücken', ['Bizeps'], 'Kurzhantel', 'Knie und Hand auf der Bank, Hantel eng am Körper zur Hüfte ziehen.', false, 120],
  ['T-Bar-Rudern', 'Rücken', ['Bizeps'], 'Langhantel', 'Landmine oder T-Bar-Station, Brust raus, Griffe zum Bauch ziehen.', false, 150],
  ['Kabelrudern (sitzend)', 'Rücken', ['Bizeps'], 'Kabel', 'Aufrecht sitzen, Griff zum Bauch, Schulterblätter am Ende zusammenziehen.', false, 120],
  ['Kabelrudern (einarmig)', 'Rücken', ['Bizeps'], 'Kabel', 'Einarmig mit leichter Rotation — größerer Bewegungsumfang.', false, 90],
  ['Maschinenrudern', 'Rücken', ['Bizeps'], 'Maschine', 'Brust am Polster, Griffe nach hinten ziehen, Ellbogen eng führen.', false, 120],
  ['Überzüge am Kabel (gestreckte Arme)', 'Rücken', [], 'Kabel', 'Arme fast gestreckt, Stange im Bogen zu den Oberschenkeln ziehen. Isolation für den Lat.', false, 90],
  ['Kreuzheben (konventionell)', 'Rücken', ['Hamstrings', 'Gesäß', 'Quadrizeps', 'Unterarme'], 'Langhantel', 'Stange über Mittelfuß, Rücken neutral, mit Beinen andrücken und Hüfte durchstrecken.', false, 210],
  ['Sumo-Kreuzheben', 'Rücken', ['Quadrizeps', 'Gesäß', 'Hamstrings'], 'Langhantel', 'Weiter Stand, Griff innerhalb der Beine, Brust hoch, Hüfte nah an der Stange.', false, 210],
  ['Rack Pulls', 'Rücken', ['Hamstrings', 'Gesäß'], 'Langhantel', 'Kreuzheben aus erhöhter Position (Kniehöhe) — schwere Teilwiederholungen.', false, 180],
  ['Hyperextensions (Rückenstrecker)', 'Rücken', ['Gesäß', 'Hamstrings'], 'Körpergewicht', 'Oberkörper langsam senken und bis zur Körperlinie aufrichten — nicht überstrecken.', false, 90],
  ['Nackenziehen / Shrugs (Langhantel)', 'Rücken', ['Unterarme'], 'Langhantel', 'Schultern gerade nach oben ziehen, oben 1 Sek. halten. Kein Kreisen.', false, 90],
  ['Shrugs (Kurzhantel)', 'Rücken', ['Unterarme'], 'Kurzhantel', 'Hanteln seitlich, Schultern maximal Richtung Ohren ziehen.', false, 90],
  ['Inverted Rows (Australian Pull-ups)', 'Rücken', ['Bizeps'], 'Körpergewicht', 'Unter einer Stange hängen, Körper gerade, Brust zur Stange ziehen.', false, 90],
  ['Meadows Row', 'Rücken', ['Bizeps'], 'Langhantel', 'Landmine seitlich greifen, einarmig explosiv zur Hüfte ziehen.', false, 120],
  ['Face Pulls', 'Schultern', ['Rücken'], 'Kabel', 'Seil auf Gesichtshöhe, zum Gesicht ziehen und Ellbogen weit nach außen — top für die Haltung.', false, 90],
  ['Reverse Flys (Kurzhantel)', 'Schultern', ['Rücken'], 'Kurzhantel', 'Vorgebeugt, Arme im Bogen nach außen öffnen. Hintere Schulter isolieren.', false, 90],

  // ── Schultern ────────────────────────────────────────────────────────────
  ['Schulterdrücken (Langhantel, stehend)', 'Schultern', ['Trizeps', 'Bauch'], 'Langhantel', 'Stange von der Brust über den Kopf drücken, Gesäß und Bauch fest anspannen.', false, 180],
  ['Schulterdrücken (Kurzhantel, sitzend)', 'Schultern', ['Trizeps'], 'Kurzhantel', 'Rückenlehne steil, Hanteln von Ohrhöhe nach oben drücken.', false, 150],
  ['Arnold Press', 'Schultern', ['Trizeps'], 'Kurzhantel', 'Aus der Supination heraus drehen und drücken — trifft alle drei Schulterköpfe.', false, 150],
  ['Schulterpresse (Maschine)', 'Schultern', ['Trizeps'], 'Maschine', 'Geführtes Drücken über Kopf, Rücken bleibt am Polster.', false, 120],
  ['Push Press', 'Schultern', ['Trizeps', 'Quadrizeps'], 'Langhantel', 'Leichter Impuls aus den Beinen, dann explosiv über Kopf drücken.', false, 180],
  ['Seitheben (Kurzhantel)', 'Schultern', [], 'Kurzhantel', 'Leicht gebeugte Arme bis Schulterhöhe heben, kleiner Finger leicht führen. Kein Schwung.', false, 75],
  ['Seitheben (Kabel)', 'Schultern', [], 'Kabel', 'Zug unten, hinter dem Körper vorbei seitlich heben — konstante Spannung.', false, 75],
  ['Seitheben (Maschine)', 'Schultern', [], 'Maschine', 'Ellbogen am Polster, kontrolliert bis Schulterhöhe.', false, 75],
  ['Frontheben (Kurzhantel)', 'Schultern', [], 'Kurzhantel', 'Arme abwechselnd nach vorn bis Schulterhöhe heben, Rumpf bleibt ruhig.', false, 75],
  ['Frontheben (Langhantel)', 'Schultern', [], 'Langhantel', 'Beide Arme gleichzeitig bis Schulterhöhe, kein Zurücklehnen.', false, 75],
  ['Reverse Butterfly (Maschine)', 'Schultern', ['Rücken'], 'Maschine', 'Brust am Polster, Arme nach hinten öffnen. Hintere Schulter.', false, 75],
  ['Aufrechtes Rudern', 'Schultern', ['Bizeps', 'Rücken'], 'Langhantel', 'Stange eng am Körper bis Brusthöhe ziehen, Ellbogen führen. Bei Schmerzen weglassen.', false, 90],
  ['Handstand-Liegestütze', 'Schultern', ['Trizeps'], 'Körpergewicht', 'An der Wand, kontrolliert absenken bis der Kopf fast den Boden berührt.', false, 180],
  ['Landmine Press', 'Schultern', ['Brust', 'Trizeps'], 'Langhantel', 'Einarmig schräg nach oben drücken — schulterfreundlich.', false, 120],
  ['Außenrotation am Kabel', 'Schultern', [], 'Kabel', 'Ellbogen 90° am Körper fixiert, Unterarm nach außen rotieren. Rotatorenmanschette.', false, 60],

  // ── Bizeps ───────────────────────────────────────────────────────────────
  ['Langhantel-Curls', 'Bizeps', ['Unterarme'], 'Langhantel', 'Ellbogen am Körper fixiert, nur der Unterarm bewegt sich. Kein Schwung aus der Hüfte.', false, 90],
  ['SZ-Stange Curls', 'Bizeps', ['Unterarme'], 'Langhantel', 'Gewinkelte Stange schont die Handgelenke. Kontrolliert ablassen.', false, 90],
  ['Kurzhantel-Curls', 'Bizeps', ['Unterarme'], 'Kurzhantel', 'Beim Beugen leicht nach außen drehen (Supination), oben kurz anspannen.', false, 75],
  ['Hammer-Curls', 'Bizeps', ['Unterarme'], 'Kurzhantel', 'Neutraler Griff (Daumen oben) — trifft Brachialis und Unterarm.', false, 75],
  ['Konzentrationscurls', 'Bizeps', [], 'Kurzhantel', 'Ellbogen am Innenschenkel abstützen, langsam beugen — maximale Isolation.', false, 75],
  ['Schrägbank-Curls', 'Bizeps', [], 'Kurzhantel', 'Auf 45°-Bank zurücklehnen, Arme hängen — starke Dehnung im langen Bizepskopf.', false, 75],
  ['Scott-Curls (Preacher)', 'Bizeps', [], 'Langhantel', 'Oberarme fest am Pult, unten nicht ganz durchstrecken.', false, 90],
  ['Kabel-Curls', 'Bizeps', ['Unterarme'], 'Kabel', 'Konstante Spannung über den gesamten Bewegungsumfang.', false, 75],
  ['Seil-Hammercurls (Kabel)', 'Bizeps', ['Unterarme'], 'Kabel', 'Seil am unteren Zug, Handflächen zueinander, oben Seil auseinanderziehen.', false, 75],
  ['Spider-Curls', 'Bizeps', [], 'Kurzhantel', 'Bauchlage auf der Schrägbank, Arme senkrecht hängend curlen.', false, 75],
  ['Reverse Curls', 'Unterarme', ['Bizeps'], 'Langhantel', 'Obergriff — trainiert Brachioradialis und Unterarmstrecker.', false, 75],
  ['Bizeps-Maschine', 'Bizeps', [], 'Maschine', 'Oberarme fixiert, geführte Bewegung, ideal für Endsätze.', false, 75],

  // ── Trizeps ──────────────────────────────────────────────────────────────
  ['Trizepsdrücken am Kabel (Seil)', 'Trizeps', [], 'Kabel', 'Ellbogen am Körper, unten Seil auseinanderziehen und 1 Sek. halten.', false, 75],
  ['Trizepsdrücken am Kabel (Stange)', 'Trizeps', [], 'Kabel', 'Gerade Stange, Ellbogen fixiert, voll durchstrecken.', false, 75],
  ['Trizepsdrücken über Kopf (Kabel)', 'Trizeps', [], 'Kabel', 'Vom Zug wegdrehen, Seil hinter dem Kopf nach oben strecken — dehnt den langen Kopf.', false, 75],
  ['Skull Crushers (SZ-Stange)', 'Trizeps', [], 'Langhantel', 'Liegend, Stange zur Stirn/hinter den Kopf senken, Oberarme bleiben senkrecht.', false, 90],
  ['Enges Bankdrücken', 'Trizeps', ['Brust', 'Schultern'], 'Langhantel', 'Schulterbreiter Griff, Ellbogen eng am Körper führen.', false, 150],
  ['Dips (Barren)', 'Trizeps', ['Brust', 'Schultern'], 'Körpergewicht', 'Oberkörper aufrecht halten, bis 90° im Ellbogen absenken.', false, 150],
  ['Bank-Dips', 'Trizeps', ['Schultern'], 'Körpergewicht', 'Hände hinter dem Körper auf der Bank, Gesäß nah an der Bank absenken.', false, 90],
  ['Kickbacks (Kurzhantel)', 'Trizeps', [], 'Kurzhantel', 'Oberarm parallel zum Boden fixiert, nur den Unterarm strecken.', false, 60],
  ['Französisches Drücken (Kurzhantel)', 'Trizeps', [], 'Kurzhantel', 'Eine Hantel beidhändig hinter den Kopf senken, Ellbogen eng.', false, 90],
  ['Trizeps-Maschine', 'Trizeps', [], 'Maschine', 'Geführtes Strecken, sauber kontrolliert zurückführen.', false, 75],
  ['JM Press', 'Trizeps', ['Brust'], 'Langhantel', 'Mischung aus engem Bankdrücken und Skull Crusher — Stange zum Hals/Kinn.', false, 120],
  ['Reverse-Grip Pushdown', 'Trizeps', [], 'Kabel', 'Untergriff am Kabel — betont den medialen Trizepskopf.', false, 75],

  // ── Quadrizeps ───────────────────────────────────────────────────────────
  ['Kniebeugen (Langhantel)', 'Quadrizeps', ['Gesäß', 'Hamstrings', 'Bauch'], 'Langhantel', 'Stange auf dem Trapez, Knie in Fußrichtung, mindestens bis parallel absenken.', false, 210],
  ['Frontkniebeugen', 'Quadrizeps', ['Bauch', 'Gesäß'], 'Langhantel', 'Stange vorn auf den Schultern, Ellbogen hoch, Oberkörper aufrecht.', false, 180],
  ['Hackenschmidt-Kniebeuge', 'Quadrizeps', ['Gesäß'], 'Maschine', 'Rücken am Polster, Füße mittig, tief absenken — starker Quad-Reiz.', false, 150],
  ['Beinpresse', 'Quadrizeps', ['Gesäß', 'Hamstrings'], 'Maschine', 'Füße schulterbreit, Knie nicht ganz durchstrecken, Rücken bleibt am Polster.', false, 150],
  ['Beinstrecker', 'Quadrizeps', [], 'Maschine', 'Oben 1 Sek. halten, langsam ablassen. Isolation für den Quadrizeps.', false, 90],
  ['Ausfallschritte (Kurzhantel)', 'Quadrizeps', ['Gesäß', 'Hamstrings'], 'Kurzhantel', 'Großer Schritt nach vorn, hinteres Knie Richtung Boden, Oberkörper aufrecht.', false, 120],
  ['Walking Lunges', 'Quadrizeps', ['Gesäß'], 'Kurzhantel', 'Ausfallschritte in Bewegung, abwechselnd links/rechts.', false, 120],
  ['Bulgarian Split Squat', 'Quadrizeps', ['Gesäß'], 'Kurzhantel', 'Hinterer Fuß erhöht, tief absenken. Sehr intensiv pro Bein.', false, 150],
  ['Goblet Squat', 'Quadrizeps', ['Gesäß', 'Bauch'], 'Kurzhantel', 'Hantel vor der Brust halten, tief beugen, Oberkörper aufrecht.', false, 120],
  ['Step-ups', 'Quadrizeps', ['Gesäß'], 'Kurzhantel', 'Auf eine Box steigen, Kraft über die Ferse des vorderen Beins.', false, 120],
  ['Sissy Squat', 'Quadrizeps', [], 'Körpergewicht', 'Knie nach vorn schieben, Oberkörper zurücklehnen — starke Quad-Dehnung.', false, 90],
  ['Kniebeugen (Smith-Maschine)', 'Quadrizeps', ['Gesäß'], 'Maschine', 'Geführte Kniebeuge, Füße etwas weiter vorn.', false, 150],
  ['Box Squats', 'Quadrizeps', ['Gesäß'], 'Langhantel', 'Auf eine Box setzen, kurz Spannung halten, explosiv hoch.', false, 180],
  ['Pistol Squat', 'Quadrizeps', ['Gesäß', 'Bauch'], 'Körpergewicht', 'Einbeinige Kniebeuge, freies Bein nach vorn gestreckt.', false, 150],
  ['Wandsitzen', 'Quadrizeps', ['Gesäß'], 'Körpergewicht', 'Rücken an der Wand, Oberschenkel parallel zum Boden, Position halten.', true, 90],
  ['Adduktoren-Maschine', 'Quadrizeps', ['Gesäß'], 'Maschine', 'Beine gegen den Widerstand zusammenführen — Innenschenkel.', false, 75],

  // ── Hamstrings ───────────────────────────────────────────────────────────
  ['Beinbeuger (liegend)', 'Hamstrings', ['Waden'], 'Maschine', 'Hüfte am Polster, Fersen zum Gesäß ziehen, langsam ablassen.', false, 90],
  ['Beinbeuger (sitzend)', 'Hamstrings', [], 'Maschine', 'Polster über den Knien fixieren, kraftvoll beugen, kontrolliert zurück.', false, 90],
  ['Rumänisches Kreuzheben (Langhantel)', 'Hamstrings', ['Gesäß', 'Rücken'], 'Langhantel', 'Knie leicht gebeugt, Hüfte nach hinten schieben, Stange eng am Bein — Dehnung spüren.', false, 150],
  ['Rumänisches Kreuzheben (Kurzhantel)', 'Hamstrings', ['Gesäß'], 'Kurzhantel', 'Wie mit der Langhantel, größerer Bewegungsumfang möglich.', false, 120],
  ['Kreuzheben mit gestreckten Beinen', 'Hamstrings', ['Rücken', 'Gesäß'], 'Langhantel', 'Beine nahezu gestreckt, Rücken neutral, nur so tief wie die Dehnung erlaubt.', false, 150],
  ['Nordic Curls', 'Hamstrings', ['Gesäß'], 'Körpergewicht', 'Füße fixieren, Oberkörper langsam nach vorn absenken — exzentrisch bremsen.', false, 150],
  ['Glute-Ham Raise', 'Hamstrings', ['Gesäß', 'Rücken'], 'Körpergewicht', 'An der GHR-Bank Oberkörper senken und über die Beinbeuger wieder aufrichten.', false, 150],
  ['Good Mornings', 'Hamstrings', ['Rücken', 'Gesäß'], 'Langhantel', 'Stange im Nacken, Hüfte nach hinten, Rücken bleibt gerade. Leichtes Gewicht.', false, 120],

  // ── Gesäß ────────────────────────────────────────────────────────────────
  ['Hip Thrust (Langhantel)', 'Gesäß', ['Hamstrings'], 'Langhantel', 'Schulterblätter auf der Bank, Hüfte bis zur Körperlinie strecken, oben anspannen.', false, 150],
  ['Glute Bridge', 'Gesäß', ['Hamstrings'], 'Körpergewicht', 'Rückenlage, Hüfte anheben bis Schulter–Knie eine Linie bilden.', false, 90],
  ['Hip Thrust (Maschine)', 'Gesäß', ['Hamstrings'], 'Maschine', 'Geführter Hip Thrust, Rücken bleibt neutral.', false, 120],
  ['Einbeiniger Hip Thrust', 'Gesäß', ['Hamstrings'], 'Körpergewicht', 'Ein Bein angehoben, Hüfte einbeinig strecken.', false, 90],
  ['Kabel-Kickbacks', 'Gesäß', ['Hamstrings'], 'Kabel', 'Fußmanschette am unteren Zug, Bein nach hinten strecken, oben anspannen.', false, 75],
  ['Abduktoren-Maschine', 'Gesäß', [], 'Maschine', 'Beine gegen den Widerstand nach außen drücken — Gesäßmuskulatur seitlich.', false, 75],
  ['Kettlebell Swing', 'Gesäß', ['Hamstrings', 'Rücken'], 'Kurzhantel', 'Kraft aus der Hüfte (Hip Hinge), Kettlebell schwingt bis Brusthöhe.', false, 90],
  ['Sumo Goblet Squat', 'Gesäß', ['Quadrizeps'], 'Kurzhantel', 'Weiter Stand, Zehen nach außen, Hantel vor der Brust.', false, 120],
  ['Frog Pumps', 'Gesäß', [], 'Körpergewicht', 'Fußsohlen zusammen, Knie außen, Hüfte pulsierend anheben.', false, 60],

  // ── Waden ────────────────────────────────────────────────────────────────
  ['Wadenheben (stehend)', 'Waden', [], 'Maschine', 'Ferse tief absenken, langsam bis auf die Zehenspitzen. Oben 1 Sek. halten.', false, 75],
  ['Wadenheben (sitzend)', 'Waden', [], 'Maschine', 'Knie gebeugt — trifft den Soleus. Voller Bewegungsumfang.', false, 75],
  ['Wadenheben in der Beinpresse', 'Waden', [], 'Maschine', 'Nur die Fußballen auf der Platte, Knie fast gestreckt.', false, 75],
  ['Wadenheben (Kurzhantel)', 'Waden', [], 'Kurzhantel', 'Einbeinig auf einer Erhöhung, Hantel in der Hand.', false, 60],
  ['Eselwadenheben', 'Waden', [], 'Körpergewicht', 'Oberkörper vorgebeugt abgestützt, Ferse tief, dann hoch.', false, 60],
  ['Wadenheben (Smith-Maschine)', 'Waden', [], 'Maschine', 'Fußballen auf einer Erhöhung, Stange im Nacken.', false, 75],

  // ── Bauch ────────────────────────────────────────────────────────────────
  ['Crunches', 'Bauch', [], 'Körpergewicht', 'Nur Schulterblätter vom Boden lösen, Bauch bewusst zusammenziehen.', false, 60],
  ['Sit-ups', 'Bauch', [], 'Körpergewicht', 'Kompletter Aufrichter, Hände an den Schläfen, Nacken locker.', false, 60],
  ['Beinheben (hängend)', 'Bauch', ['Unterarme'], 'Körpergewicht', 'An der Stange hängend Beine gestreckt anheben, kein Schwung.', false, 90],
  ['Knieheben (hängend)', 'Bauch', [], 'Körpergewicht', 'Knie zur Brust ziehen, Becken am Ende leicht aufrollen.', false, 75],
  ['Toes to Bar', 'Bauch', ['Rücken', 'Unterarme'], 'Körpergewicht', 'Aus dem Hang die Füße zur Stange führen.', false, 90],
  ['Plank (Unterarmstütz)', 'Bauch', ['Schultern'], 'Körpergewicht', 'Körper bildet eine gerade Linie, Gesäß und Bauch fest anspannen.', true, 60],
  ['Seitlicher Plank', 'Bauch', ['Schultern'], 'Körpergewicht', 'Auf einem Unterarm seitlich stützen, Hüfte oben halten.', true, 60],
  ['Hollow Hold', 'Bauch', [], 'Körpergewicht', 'Rückenlage, Arme und Beine angehoben, unterer Rücken bleibt am Boden.', true, 60],
  ['Mountain Climbers', 'Bauch', ['Quadrizeps', 'Schultern'], 'Körpergewicht', 'Aus dem Liegestütz Knie abwechselnd zur Brust ziehen.', true, 60],
  ['Russian Twists', 'Bauch', [], 'Körpergewicht', 'Sitzend zurücklehnen, Oberkörper kontrolliert rotieren.', false, 60],
  ['Ab Wheel Rollout', 'Bauch', ['Schultern', 'Rücken'], 'Körpergewicht', 'Aus dem Knien nach vorn rollen, unteren Rücken nicht durchhängen lassen.', false, 90],
  ['Kabel-Crunches', 'Bauch', [], 'Kabel', 'Kniend am Seil, Oberkörper einrollen — Zug kommt aus dem Bauch, nicht aus der Hüfte.', false, 75],
  ['Bicycle Crunches', 'Bauch', [], 'Körpergewicht', 'Ellbogen und gegenüberliegendes Knie zusammenführen, im Wechsel.', false, 60],
  ['Beinheben (liegend)', 'Bauch', [], 'Körpergewicht', 'Rückenlage, Beine gestreckt anheben und langsam absenken.', false, 60],
  ['Dead Bug', 'Bauch', [], 'Körpergewicht', 'Gegengleiche Arme/Beine absenken, Lendenwirbelsäule bleibt am Boden.', false, 60],
  ['V-Ups', 'Bauch', [], 'Körpergewicht', 'Arme und Beine gleichzeitig zum V zusammenführen.', false, 60],

  // ── Unterarme ────────────────────────────────────────────────────────────
  ['Handgelenk-Curls', 'Unterarme', [], 'Langhantel', 'Unterarme auf den Oberschenkeln, nur die Handgelenke beugen.', false, 60],
  ['Reverse Handgelenk-Curls', 'Unterarme', [], 'Langhantel', 'Obergriff, Handrücken nach oben strecken — Unterarmstrecker.', false, 60],
  ["Farmer's Walk", 'Unterarme', ['Rücken', 'Bauch'], 'Kurzhantel', 'Schwere Hanteln seitlich tragen, Schultern hinten, aufrecht gehen.', true, 120],
  ['Dead Hang', 'Unterarme', ['Rücken'], 'Körpergewicht', 'Einfach an der Klimmzugstange aushängen — Griffkraft und Schulterentlastung.', true, 90],
  ['Plate Pinch', 'Unterarme', [], 'Körpergewicht', 'Zwei Scheiben mit den Fingerspitzen zusammendrücken und halten.', true, 60],
  ['Handgelenk-Roller', 'Unterarme', ['Schultern'], 'Körpergewicht', 'Gewicht an einer Schnur auf- und abrollen, Arme vorgestreckt.', false, 75],

  // ── Cardio ───────────────────────────────────────────────────────────────
  ['Laufband', 'Quadrizeps', ['Waden', 'Hamstrings'], 'Cardio', 'Dauerlauf oder Intervalle. Dauer und ggf. Steigung/Tempo als Notiz erfassen.', true, 60],
  ['Rudergerät', 'Rücken', ['Quadrizeps', 'Bizeps'], 'Cardio', 'Reihenfolge Beine – Rumpf – Arme, kontrolliert zurück.', true, 60],
  ['Fahrrad-Ergometer', 'Quadrizeps', ['Waden'], 'Cardio', 'Gleichmäßige Trittfrequenz, Widerstand nach Gefühl.', true, 60],
  ['Crosstrainer', 'Quadrizeps', ['Gesäß', 'Rücken'], 'Cardio', 'Gleichmäßige Bewegung, Arme aktiv mitziehen.', true, 60],
  ['Stairmaster', 'Gesäß', ['Quadrizeps', 'Waden'], 'Cardio', 'Aufrecht bleiben, nicht auf die Griffe stützen.', true, 60],
  ['Seilspringen', 'Waden', ['Schultern'], 'Cardio', 'Kleine Sprünge aus dem Fußgelenk, Handgelenke rotieren.', true, 60],
  ['Burpees', 'Quadrizeps', ['Brust', 'Bauch', 'Schultern'], 'Cardio', 'Liegestütz, Sprung in die Hocke, Strecksprung — durchgehend flüssig.', false, 90],
  ['Schwimmen', 'Rücken', ['Schultern', 'Brust'], 'Cardio', 'Dauer und Stil frei wählbar — Ausdauer und Schultermobilität.', true, 60],
  ['Boxsack / Schattenboxen', 'Schultern', ['Bauch', 'Brust'], 'Cardio', 'Runden von 2–3 Minuten, Deckung oben halten.', true, 60],
  ['Air Bike', 'Quadrizeps', ['Rücken', 'Schultern'], 'Cardio', 'Arme und Beine gleichzeitig — sehr intensive Intervalle.', true, 60],
  ['Wandern / Zügiges Gehen', 'Quadrizeps', ['Waden', 'Gesäß'], 'Cardio', 'Lockere Grundlagenausdauer, Dauer erfassen.', true, 60],
  ['Sled Push', 'Quadrizeps', ['Gesäß', 'Waden'], 'Cardio', 'Schlitten mit tiefem Körperschwerpunkt schieben.', true, 120],
]

export function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/ä/g, 'ae')
    .replace(/ö/g, 'oe')
    .replace(/ü/g, 'ue')
    .replace(/ß/g, 'ss')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
}

export function buildSeedExercises(): Exercise[] {
  const now = Date.now()
  const seen = new Set<string>()
  const out: Exercise[] = []
  for (const [name, primary, secondary, category, instructions, timeBased, restSec] of S) {
    const id = `ex_${slugify(name)}`
    if (seen.has(id)) continue
    seen.add(id)
    out.push({
      id,
      name,
      primary,
      secondary,
      category,
      instructions,
      restSec: restSec ?? (category === 'Cardio' ? 60 : 90),
      timeBased: timeBased ?? false,
      custom: false,
      createdAt: now,
      updatedAt: now,
    })
  }
  return out
}

export const SEED_COUNT = new Set(S.map(([n]) => `ex_${slugify(n)}`)).size
