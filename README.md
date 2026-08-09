# Lift — privater Workout-Tracker (PWA)

Ein kompletter Trainingstagebuch fürs iPhone, der **komplett offline auf deinem Gerät** läuft.
Kein Konto, keine Werbung, kein Tracking, keine Paywall, keine Limits. Alle Daten bleiben lokal
im Browser-Speicher (IndexedDB) — zusätzlich kannst du jederzeit ein Backup als Datei sichern.

---

## Was die App kann

| Bereich | Funktionen |
|---|---|
| **Übungen** | 155 vordefinierte Übungen mit Kurzanleitung, Zielmuskeln und Standard-Pausenzeit · Suche nach Name oder Muskel · eigene Übungen anlegen, bearbeiten, löschen |
| **Routinen** | Vorlagen mit Ziel-Sätzen/Wiederholungen · Reihenfolge per Drag & Drop |
| **Programme** | Routinen bündeln (z. B. Push/Pull/Legs) · Generator nach Ziel (Kraft/Muskelaufbau/Kraftausdauer), Tagen pro Woche und Equipment |
| **Workout** | Start aus Routine oder freestyle · Gewicht, Wdh., RPE, Warmup-/Dropset-Markierung · Übungen und Sätze während des Trainings hinzufügen, entfernen, umsortieren · Vorschläge aus dem letzten Workout |
| **Pausen-Timer** | Startet automatisch nach jedem abgehakten Satz · Countdown mit Ring, ±15 s, überspringen · Vibration + Ton |
| **Zeit-Übungen** | Dauer statt Wiederholungen (Plank, Cardio, …) |
| **Zusammenfassung** | Volumen, Dauer, Sätze und alle neuen Rekorde nach dem Beenden |
| **Statistiken** | Fortschritt je Übung (Gewicht, geschätztes 1RM nach Epley, Volumen) · Wochenvolumen · Workouts pro Woche · Muskelverteilung · Konsistenz-Heatmap · Rekord-Verlauf |
| **Muskel-Erholung** | Schätzung, wie erholt jede Muskelgruppe ist (48–72 Std. nach der letzten Belastung) |
| **Rekorde & Erfolge** | PRs werden automatisch erkannt (Meldung direkt im Workout) · 21 Erfolge · Wochen-Streak |
| **Verlauf** | Listen- und Kalenderansicht · vergangene Workouts ansehen, bearbeiten, löschen |
| **Körperdaten** | Gewicht, Körperfett und Maße erfassen · Verlauf als Graph |
| **Extras** | kg/lb-Umschaltung · Hantelscheiben-Rechner · Backup-Export/-Import |

---

## Auf dem iPhone installieren

1. Die HTTPS-Adresse der App **in Safari** öffnen (nicht in Chrome — nur Safari kann auf iOS installieren).
2. Unten auf das **Teilen-Symbol** (Quadrat mit Pfeil nach oben) tippen.
3. **„Zum Home-Bildschirm"** wählen → **„Hinzufügen"**.
4. Die App startet ab jetzt über das Lift-Icon im Vollbild — ohne Safari-Leiste, und auch **ohne Internet**.

> Beim ersten Start braucht die App einmal Internet, um sich zu laden. Danach funktioniert alles offline.

---

## Backup — bitte regelmäßig machen

Deine Daten liegen nur auf dem iPhone. Wenn du die App vom Home-Bildschirm löschst oder iOS den
Speicher aufräumt, sind sie weg. Deshalb:

**Backup erstellen:** `Mehr` → `Datensicherung` → **Backup exportieren**.
Auf dem iPhone öffnet sich das Teilen-Menü — sichere die Datei z. B. in **„Dateien" → iCloud Drive**.

**Backup zurückspielen:** `Mehr` → `Datensicherung` → **Backup importieren** → Datei auswählen →
`Alles ersetzen` (exakter Stand des Backups) oder `Fehlende Daten ergänzen`.

Die App erinnert dich automatisch, wenn das letzte Backup zu lange her ist (Intervall einstellbar,
Standard 14 Tage). Zusätzlich fordert die App beim Start `navigator.storage.persist()` an, damit iOS
die Daten nicht automatisch löscht.

---

## Lokal starten und bauen

Voraussetzung: [Node.js](https://nodejs.org) ab Version 20.

```bash
npm install       # Abhängigkeiten installieren (einmalig)
npm run dev       # Entwicklungsserver, öffnet http://localhost:5173/gymapp/
npm run build     # Produktions-Build nach dist/
npm run preview   # gebaute App lokal testen
```

Icons neu erzeugen (nur nötig, wenn du das Logo änderst):

```bash
node scripts/make-icons.mjs
```

---

## Deployment

### GitHub Pages (eingerichtet)

Die Datei `.github/workflows/deploy.yml` baut und veröffentlicht die App automatisch bei jedem Push.
Einmalig muss GitHub Pages aktiviert werden:

1. Repository auf github.com öffnen → Reiter **Settings**.
2. Links **Pages** anklicken.
3. Bei **Source** **„GitHub Actions"** auswählen.
4. Fertig — nach dem nächsten Push (oder unter *Actions* → *Deploy zu GitHub Pages* → *Run workflow*)
   ist die App erreichbar unter:
   `https://<dein-benutzername>.github.io/gymapp/`

### Alternative: Netlify oder Vercel

Beide Dienste liefern die App unter einer eigenen Domain im Wurzelverzeichnis aus — dafür muss der
Basis-Pfad auf `/` gesetzt werden:

* **Build-Befehl:** `npm run build`
* **Publish-Verzeichnis:** `dist`
* **Umgebungsvariable:** `BASE_PATH` = `/`

---

## Technik

* **React 19 + TypeScript + Vite 8**
* **Tailwind CSS 4** (dunkles Theme, Safe-Area-Insets, große Tap-Flächen)
* **Dexie.js** für IndexedDB — jede Änderung wird sofort geschrieben
* **vite-plugin-pwa / Workbox** — Service Worker, Web-Manifest, vollständig offline
* **Recharts** für die Diagramme, **dnd-kit** für Drag & Drop
* Kein Backend, keine externen Requests, keine Analytics

### Projektstruktur

```
src/
  db/          Dexie-Schema, Typen, 155 vordefinierte Übungen
  lib/         Berechnungen (1RM, Volumen, Scheiben), PRs, Erfolge,
               Erholung, Backup, Programm-Generator, Haptik/Ton
  state/       App-Einstellungen und der laufende Workout-Zustand
  components/  UI-Bausteine, Diagramme, Pausen-Timer, Übungsauswahl
  screens/     Start · Workout · Zusammenfassung · Verlauf · Statistik ·
               Übungen · Routinen · Programme · Körperdaten · Erfolge · Einstellungen
```

Alle Grafiken (App-Icon, Symbole) sind selbst erzeugt — es werden keine geschützten Inhalte
anderer Apps verwendet.
