import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useLiveQuery } from 'dexie-react-hooks'
import { db, initDb, requestPersistentStorage, storageEstimate } from '../db/db'
import type { BackupFile, Unit } from '../db/types'
import { ConfirmDialog, Divider, Row, Screen, Section, Sheet, Stepper, Toggle } from '../components/ui'
import { PlateCalculator } from '../components/PlateCalculator'
import { useApp } from '../state/AppState'
import { downloadBackup, parseBackup, restoreBackup, shareBackup, daysSince } from '../lib/backup'
import type { ImportMode } from '../lib/backup'
import { recomputeAllPRs } from '../lib/pr'
import { trimNum } from '../lib/calc'
import { haptic } from '../lib/feedback'
import { SEED_COUNT } from '../db/seedExercises'

const PLATE_OPTIONS = [25, 20, 15, 10, 5, 2.5, 1.25, 1, 0.5]

export default function SettingsScreen() {
  const navigate = useNavigate()
  const { settings, updateSettings, pushToast } = useApp()
  const fileRef = useRef<HTMLInputElement>(null)

  const [storage, setStorage] = useState<{ usage: number; quota: number } | null>(null)
  const [pending, setPending] = useState<BackupFile | null>(null)
  const [plateOpen, setPlateOpen] = useState(false)
  const [equipOpen, setEquipOpen] = useState(false)
  const [confirmReset, setConfirmReset] = useState(false)
  const [busy, setBusy] = useState(false)

  const counts = useLiveQuery(async () => {
    const [sessions, sets, exercises, routines, body] = await Promise.all([
      db.sessions.count(),
      db.sets.count(),
      db.exercises.count(),
      db.routines.count(),
      db.bodyMetrics.count(),
    ])
    return { sessions, sets, exercises, routines, body }
  }, [])

  useEffect(() => {
    void storageEstimate().then(setStorage)
  }, [counts])

  const exportBackup = async () => {
    if (busy) return
    setBusy(true)
    try {
      const shared = await shareBackup()
      if (!shared) {
        const { filename } = await downloadBackup()
        pushToast({ kind: 'success', title: 'Backup gespeichert', message: filename })
      } else {
        pushToast({ kind: 'success', title: 'Backup geteilt' })
      }
    } catch (err) {
      console.error(err)
      pushToast({ kind: 'error', title: 'Export fehlgeschlagen' })
    } finally {
      setBusy(false)
    }
  }

  const onFile = async (file: File | undefined) => {
    if (!file) return
    try {
      const text = await file.text()
      setPending(parseBackup(text))
    } catch (err) {
      pushToast({
        kind: 'error',
        title: 'Import fehlgeschlagen',
        message: err instanceof Error ? err.message : 'Unbekannter Fehler',
      })
    } finally {
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const doImport = async (mode: ImportMode) => {
    if (!pending || busy) return
    setBusy(true)
    try {
      const result = await restoreBackup(pending, mode)
      await initDb()
      setPending(null)
      pushToast({
        kind: 'success',
        title: 'Backup wiederhergestellt',
        message: `${result.sessions} Workouts, ${result.sets} Sätze`,
      })
    } catch (err) {
      console.error(err)
      pushToast({ kind: 'error', title: 'Import fehlgeschlagen' })
    } finally {
      setBusy(false)
    }
  }

  const backupAge = daysSince(settings.lastBackupAt)
  const mb = (n: number) => `${Math.round((n / 1024 / 1024) * 10) / 10} MB`

  return (
    <Screen title="Einstellungen">
      <Section title="Einheiten & Training">
        <div className="card overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3.5">
            <span>Einheit</span>
            <div className="flex gap-2">
              {(['kg', 'lb'] as Unit[]).map((u) => (
                <button
                  key={u}
                  className={`chip ${settings.unit === u ? 'chip-active' : ''}`}
                  onClick={() => {
                    haptic()
                    void updateSettings({ unit: u })
                  }}
                >
                  {u}
                </button>
              ))}
            </div>
          </div>
          <Divider />
          <div className="px-4 py-3.5">
            <Stepper
              label="Standard-Pausenzeit"
              value={settings.defaultRestSec}
              step={15}
              min={0}
              max={600}
              suffix="Sek"
              onChange={(v) => void updateSettings({ defaultRestSec: v })}
            />
          </div>
          <Divider />
          <div className="px-4 py-3.5">
            <Stepper
              label="Wochenziel (Workouts)"
              value={settings.weeklyGoal}
              min={0}
              max={14}
              onChange={(v) => void updateSettings({ weeklyGoal: v })}
            />
          </div>
          <Divider />
          <div className="px-4">
            <Toggle
              checked={settings.restTimerAutoStart}
              onChange={(v) => void updateSettings({ restTimerAutoStart: v })}
              label="Pausen-Timer automatisch starten"
              hint="Startet nach jedem abgehakten Satz."
            />
          </div>
          <Divider />
          <div className="px-4">
            <Toggle
              checked={settings.vibration}
              onChange={(v) => void updateSettings({ vibration: v })}
              label="Vibration"
              hint="Nutzt die Vibration-API, sofern das Gerät sie unterstützt."
            />
          </div>
          <Divider />
          <div className="px-4">
            <Toggle
              checked={settings.sound}
              onChange={(v) => void updateSettings({ sound: v })}
              label="Ton beim Timer-Ende"
            />
          </div>
        </div>
      </Section>

      <Section title="Hantelscheiben">
        <div className="card overflow-hidden">
          <Row onClick={() => setPlateOpen(true)} chevron>
            <span>Scheiben-Rechner öffnen</span>
          </Row>
          <Divider />
          <Row onClick={() => setEquipOpen(true)} chevron>
            <span>Stange & verfügbare Scheiben</span>
            <span className="mt-0.5 block text-xs text-mute">
              Stange {trimNum(settings.barWeight)} kg · {settings.plates.length} Scheibengrößen
            </span>
          </Row>
        </div>
      </Section>

      <Section title="Datensicherung">
        <div className="card overflow-hidden">
          <Row onClick={exportBackup} chevron>
            <span className="font-medium">Backup exportieren</span>
            <span className="mt-0.5 block text-xs text-mute">
              {backupAge === null
                ? 'Noch nie exportiert — jetzt sichern.'
                : backupAge === 0
                  ? 'Zuletzt heute gesichert.'
                  : `Zuletzt vor ${backupAge} Tagen gesichert.`}
            </span>
          </Row>
          <Divider />
          <Row onClick={() => fileRef.current?.click()} chevron>
            <span className="font-medium">Backup importieren</span>
            <span className="mt-0.5 block text-xs text-mute">Aus einer zuvor exportierten JSON-Datei.</span>
          </Row>
          <Divider />
          <div className="px-4 py-3.5">
            <Stepper
              label="Backup-Erinnerung (Tage, 0 = aus)"
              value={settings.backupReminderDays}
              min={0}
              max={90}
              step={7}
              onChange={(v) => void updateSettings({ backupReminderDays: v })}
            />
          </div>
        </div>
        <input
          ref={fileRef}
          type="file"
          accept="application/json,.json"
          className="hidden"
          onChange={(e) => void onFile(e.target.files?.[0])}
        />
        <p className="mt-2 px-1 text-xs leading-relaxed text-mute">
          Alle Daten liegen ausschließlich auf diesem Gerät. Ein Export schützt zusätzlich vor Datenverlust bei
          Neuinstallation — sichere die Datei z. B. in „Dateien" oder iCloud Drive.
        </p>
      </Section>

      <Section title="Speicher">
        <div className="card p-4">
          <div className="flex justify-between text-sm">
            <span className="text-mute">Dauerhafter Speicher</span>
            <span className={settings.persistedStorage ? 'text-green-400' : 'text-amber-400'}>
              {settings.persistedStorage ? 'aktiv' : 'nicht bestätigt'}
            </span>
          </div>
          {storage && (
            <div className="mt-2 flex justify-between text-sm">
              <span className="text-mute">Belegt</span>
              <span className="tnum">
                {mb(storage.usage)}
                {storage.quota > 0 && ` von ${mb(storage.quota)}`}
              </span>
            </div>
          )}
          {counts && (
            <div className="mt-3 border-t border-ink-700 pt-3 text-sm text-mute">
              {counts.sessions} Workouts · {counts.sets} Sätze · {counts.exercises} Übungen ·{' '}
              {counts.routines} Routinen · {counts.body} Körperdaten
            </div>
          )}
          {!settings.persistedStorage && (
            <button
              className="btn-secondary mt-3 w-full text-sm"
              onClick={async () => {
                const ok = await requestPersistentStorage()
                await updateSettings({ persistedStorage: ok })
                pushToast({
                  kind: ok ? 'success' : 'info',
                  title: ok ? 'Dauerhafter Speicher aktiv' : 'Vom Browser nicht bestätigt',
                  message: ok
                    ? undefined
                    : 'Installiere die App auf dem Home-Bildschirm und exportiere regelmäßig ein Backup.',
                })
              }}
            >
              Dauerhaften Speicher anfordern
            </button>
          )}
        </div>
      </Section>

      <Section title="Daten">
        <div className="card overflow-hidden">
          <Row
            onClick={async () => {
              await recomputeAllPRs()
              pushToast({ kind: 'success', title: 'Rekorde neu berechnet' })
            }}
            chevron
          >
            <span>Rekorde neu berechnen</span>
          </Row>
          <Divider />
          <Row
            onClick={async () => {
              await db.exercises.filter((e) => !!e.archived).modify({ archived: false })
              await initDb()
              pushToast({ kind: 'success', title: 'Übungsbibliothek zurückgesetzt' })
            }}
            chevron
          >
            <span>Ausgeblendete Übungen wieder anzeigen</span>
            <span className="mt-0.5 block text-xs text-mute">
              Stellt auch fehlende der {SEED_COUNT} vordefinierten Übungen wieder her.
            </span>
          </Row>
          <Divider />
          <Row onClick={() => setConfirmReset(true)} chevron>
            <span className="text-red-400">Alle Daten löschen</span>
          </Row>
        </div>
      </Section>

      <Section title="Weitere Bereiche">
        <div className="card overflow-hidden">
          <Row chevron onClick={() => navigate('/routines')}>
            <span>Routinen</span>
          </Row>
          <Divider />
          <Row chevron onClick={() => navigate('/programs')}>
            <span>Programme</span>
          </Row>
          <Divider />
          <Row chevron onClick={() => navigate('/body')}>
            <span>Körpergewicht & Maße</span>
          </Row>
          <Divider />
          <Row chevron onClick={() => navigate('/achievements')}>
            <span>Erfolge</span>
          </Row>
        </div>
      </Section>

      <Section title="Über">
        <div className="card p-4 text-sm leading-relaxed text-mute">
          <p className="font-medium text-white">Lift — privater Workout-Tracker</p>
          <p className="mt-2">
            Läuft komplett offline auf deinem Gerät. Kein Konto, keine Werbung, kein Tracking, keine Limits — und
            nichts wird an einen Server gesendet.
          </p>
          <p className="mt-2">
            Tipp: Über „Teilen → Zum Home-Bildschirm" installierst du die App wie eine normale iPhone-App.
          </p>
        </div>
      </Section>

      <Sheet open={plateOpen} onClose={() => setPlateOpen(false)} title="Hantelscheiben-Rechner">
        <PlateCalculator />
      </Sheet>

      <Sheet open={equipOpen} onClose={() => setEquipOpen(false)} title="Stange & Scheiben">
        <div className="card mb-4 p-4">
          <Stepper
            label="Stangengewicht (kg)"
            value={settings.barWeight}
            step={2.5}
            min={0}
            max={50}
            decimals={1}
            onChange={(v) => void updateSettings({ barWeight: v })}
          />
        </div>
        <label className="label mb-2 block">Verfügbare Scheiben (kg, pro Seite)</label>
        <div className="flex flex-wrap gap-2">
          {PLATE_OPTIONS.map((p) => (
            <button
              key={p}
              className={`chip ${settings.plates.includes(p) ? 'chip-active' : ''}`}
              onClick={() => {
                const next = settings.plates.includes(p)
                  ? settings.plates.filter((x) => x !== p)
                  : [...settings.plates, p].sort((a, b) => b - a)
                void updateSettings({ plates: next })
              }}
            >
              {trimNum(p)}
            </button>
          ))}
        </div>
      </Sheet>

      <Sheet open={!!pending} onClose={() => setPending(null)} title="Backup importieren">
        {pending && (
          <div>
            <div className="card p-4 text-sm">
              <div className="text-mute">Exportiert am</div>
              <div className="font-medium">{new Date(pending.exportedAt).toLocaleString('de-DE')}</div>
              <div className="mt-3 text-mute">Enthält</div>
              <div className="font-medium">
                {pending.data.sessions?.length ?? 0} Workouts · {pending.data.sets?.length ?? 0} Sätze ·{' '}
                {pending.data.exercises?.length ?? 0} Übungen · {pending.data.routines?.length ?? 0} Routinen
              </div>
            </div>
            <div className="mt-5 space-y-2.5">
              <button className="btn-primary w-full" disabled={busy} onClick={() => void doImport('replace')}>
                Alles ersetzen
              </button>
              <button className="btn-secondary w-full" disabled={busy} onClick={() => void doImport('merge')}>
                Fehlende Daten ergänzen
              </button>
              <button className="btn-ghost w-full" onClick={() => setPending(null)}>
                Abbrechen
              </button>
            </div>
            <p className="mt-3 text-xs text-mute">
              „Alles ersetzen" löscht die aktuellen Daten und stellt exakt den Stand des Backups her. „Ergänzen"
              behält deine aktuellen Daten und fügt nur fehlende Einträge hinzu.
            </p>
          </div>
        )}
      </Sheet>

      <ConfirmDialog
        open={confirmReset}
        title="Wirklich alle Daten löschen?"
        message="Workouts, Routinen, Rekorde und Körperdaten werden unwiderruflich gelöscht. Exportiere vorher ein Backup!"
        confirmLabel="Alles löschen"
        onCancel={() => setConfirmReset(false)}
        onConfirm={async () => {
          setConfirmReset(false)
          await Promise.all([
            db.sessions.clear(),
            db.sets.clear(),
            db.routines.clear(),
            db.programs.clear(),
            db.bodyMetrics.clear(),
            db.personalRecords.clear(),
            db.prHistory.clear(),
            db.achievements.clear(),
            db.exercises.clear(),
            db.settings.clear(),
          ])
          await initDb()
          pushToast({ kind: 'success', title: 'Alle Daten gelöscht' })
        }}
      />
    </Screen>
  )
}
