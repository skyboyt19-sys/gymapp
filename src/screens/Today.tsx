import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useLiveQuery } from 'dexie-react-hooks'
import { db } from '../db/db'
import type { Routine, WorkoutSession } from '../db/types'
import { Screen, Section, EmptyState, StatTile, Row, Divider } from '../components/ui'
import { RestTimerBar } from '../components/RestTimerBar'
import { useWorkout } from '../state/WorkoutState'
import { useApp } from '../state/AppState'
import { computeWeekStreak } from '../lib/achievements'
import { computeRecovery, recoveryColor, recoveryLabel } from '../lib/recovery'
import { formatDurationLong, relativeDays, startOfWeek, todayISO } from '../lib/format'
import { kgToDisplay, trimNum } from '../lib/calc'
import { daysSince } from '../lib/backup'
import { haptic } from '../lib/feedback'

export default function Today() {
  const navigate = useNavigate()
  const { session, startWorkout } = useWorkout()
  const { settings } = useApp()
  const [starting, setStarting] = useState(false)

  const routines = useLiveQuery(
    async () => (await db.routines.toArray()).sort((a, b) => (b.lastPerformedAt ?? 0) - (a.lastPerformedAt ?? 0)),
    [],
    [] as Routine[],
  )

  const sessions = useLiveQuery(
    async () => (await db.sessions.toArray()).filter((s) => !s.active).sort((a, b) => b.startedAt - a.startedAt),
    [],
    [] as WorkoutSession[],
  )

  const recovery = useLiveQuery(async () => {
    const [ss, sets, exercises] = await Promise.all([
      db.sessions.toArray(),
      db.sets.toArray(),
      db.exercises.toArray(),
    ])
    return computeRecovery(
      ss.filter((s) => !s.active),
      sets,
      new Map(exercises.map((e) => [e.id, e])),
    )
  }, [])

  const week = useMemo(() => {
    const from = startOfWeek(new Date()).getTime()
    const list = sessions.filter((s) => s.startedAt >= from)
    return {
      count: list.length,
      volume: list.reduce((a, s) => a + (s.totalVolume ?? 0), 0),
      sets: list.reduce((a, s) => a + (s.totalSets ?? 0), 0),
    }
  }, [sessions])

  const streak = useMemo(() => computeWeekStreak(sessions), [sessions])
  const backupAge = daysSince(settings.lastBackupAt)
  const backupDue =
    settings.backupReminderDays > 0 &&
    sessions.length > 0 &&
    (backupAge === null || backupAge >= settings.backupReminderDays)

  const start = async (routineId?: string) => {
    if (starting) return
    setStarting(true)
    haptic('success')
    try {
      await startWorkout(routineId ? { routineId } : undefined)
      navigate('/workout')
    } finally {
      setStarting(false)
    }
  }

  const greeting = (() => {
    const h = new Date().getHours()
    if (h < 5) return 'Gute Nacht'
    if (h < 11) return 'Guten Morgen'
    if (h < 18) return 'Hallo'
    return 'Guten Abend'
  })()

  return (
    <Screen
      title={greeting}
      subtitle={new Date().toLocaleDateString('de-DE', {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
      })}
    >
      {session ? (
        <button
          className="mt-2 flex w-full items-center gap-3 rounded-2xl border border-green-500/40 bg-green-600/15 p-4 text-left active:scale-[0.99] transition"
          onClick={() => navigate('/workout')}
        >
          <span className="relative flex h-3 w-3 shrink-0">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75" />
            <span className="relative inline-flex h-3 w-3 rounded-full bg-green-500" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block font-semibold truncate">{session.name}</span>
            <span className="block text-sm text-mute">Workout läuft — tippen zum Fortsetzen</span>
          </span>
          <span className="text-mute text-lg">›</span>
        </button>
      ) : (
        <button className="btn-primary mt-2 w-full text-[17px] py-4" disabled={starting} onClick={() => start()}>
          Freies Workout starten
        </button>
      )}

      {backupDue && (
        <button
          className="mt-3 flex w-full items-center gap-3 rounded-2xl border border-amber-500/40 bg-amber-500/10 p-3.5 text-left"
          onClick={() => navigate('/settings')}
        >
          <span className="text-lg">💾</span>
          <span className="min-w-0 flex-1 text-sm">
            <span className="block font-medium">Backup fällig</span>
            <span className="block text-mute">
              {backupAge === null
                ? 'Du hast noch nie ein Backup exportiert.'
                : `Letztes Backup vor ${backupAge} Tagen.`}
            </span>
          </span>
          <span className="text-mute">›</span>
        </button>
      )}

      <Section title="Diese Woche">
        <div className="grid grid-cols-3 gap-3">
          <StatTile
            label="Workouts"
            value={`${week.count}`}
            hint={settings.weeklyGoal > 0 ? `Ziel ${settings.weeklyGoal}` : undefined}
          />
          <StatTile label="Sätze" value={`${week.sets}`} />
          <StatTile
            label="Volumen"
            value={trimNum(Math.round(kgToDisplay(week.volume, settings.unit)), 0)}
            hint={settings.unit}
          />
        </div>
        {streak > 0 && (
          <div className="card mt-3 flex items-center gap-3 p-3.5">
            <span className="text-2xl">🔥</span>
            <div className="min-w-0">
              <div className="font-semibold">
                {streak} {streak === 1 ? 'Woche' : 'Wochen'} in Folge
              </div>
              <div className="text-xs text-mute">Weiter so — mindestens ein Workout pro Woche.</div>
            </div>
          </div>
        )}
      </Section>

      <Section
        title="Routinen"
        action={
          <button className="text-sm text-brand font-medium" onClick={() => navigate('/routines')}>
            Alle
          </button>
        }
      >
        {routines.length === 0 ? (
          <EmptyState
            icon="📋"
            title="Noch keine Routine"
            message="Erstelle eine Vorlage mit deinen Lieblingsübungen oder lass dir ein Programm generieren."
            action={
              <button className="btn-secondary" onClick={() => navigate('/routines')}>
                Routine erstellen
              </button>
            }
          />
        ) : (
          <div className="card overflow-hidden">
            {routines.slice(0, 5).map((r, i) => (
              <div key={r.id}>
                {i > 0 && <Divider />}
                <div className="flex items-center">
                  <button
                    className="min-w-0 flex-1 px-4 py-3.5 text-left active:bg-ink-800"
                    onClick={() => navigate(`/routines/${r.id}`)}
                  >
                    <div className="truncate font-medium">{r.name}</div>
                    <div className="text-xs text-mute mt-0.5">
                      {r.exercises.length} {r.exercises.length === 1 ? 'Übung' : 'Übungen'}
                      {r.lastPerformedAt &&
                        ` · zuletzt ${relativeDays(todayISO(new Date(r.lastPerformedAt))).toLowerCase()}`}
                    </div>
                  </button>
                  <button
                    className="btn-secondary mr-3 px-3 text-sm"
                    disabled={starting || !!session}
                    onClick={() => start(r.id)}
                  >
                    Start
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Section>

      {recovery && recovery.some((r) => r.recovery < 0.98) && (
        <Section
          title="Muskel-Erholung"
          action={
            <button className="text-sm text-brand font-medium" onClick={() => navigate('/stats')}>
              Details
            </button>
          }
        >
          <div className="card p-4">
            <div className="space-y-2.5">
              {recovery
                .slice()
                .sort((a, b) => a.recovery - b.recovery)
                .slice(0, 5)
                .map((m) => (
                  <div key={m.muscle} className="flex items-center gap-3">
                    <div className="w-24 shrink-0 truncate text-sm">{m.muscle}</div>
                    <div className="h-2 flex-1 overflow-hidden rounded-full bg-ink-700">
                      <div
                        className="h-full rounded-full transition-all"
                        style={{ width: `${Math.round(m.recovery * 100)}%`, background: recoveryColor(m.recovery) }}
                      />
                    </div>
                    <div className="w-24 shrink-0 text-right text-xs text-mute">{recoveryLabel(m.recovery)}</div>
                  </div>
                ))}
            </div>
          </div>
        </Section>
      )}

      <Section title="Zuletzt">
        {sessions.length === 0 ? (
          <EmptyState icon="🏋️" title="Noch kein Workout" message="Starte dein erstes Training — die Daten bleiben komplett auf deinem iPhone." />
        ) : (
          <div className="card overflow-hidden">
            {sessions.slice(0, 3).map((s, i) => (
              <div key={s.id}>
                {i > 0 && <Divider />}
                <Row chevron onClick={() => navigate(`/history/${s.id}`)}>
                  <div className="truncate font-medium">{s.name}</div>
                  <div className="text-xs text-mute mt-0.5">
                    {relativeDays(s.date)} · {s.totalSets ?? 0} Sätze ·{' '}
                    {formatDurationLong(s.durationSec ?? 0)}
                  </div>
                </Row>
              </div>
            ))}
          </div>
        )}
      </Section>

      <Section title="Mehr">
        <div className="card overflow-hidden">
          <Row chevron onClick={() => navigate('/programs')}>
            <span className="font-medium">Programme</span>
          </Row>
          <Divider />
          <Row chevron onClick={() => navigate('/body')}>
            <span className="font-medium">Körpergewicht & Maße</span>
          </Row>
          <Divider />
          <Row chevron onClick={() => navigate('/achievements')}>
            <span className="font-medium">Erfolge</span>
          </Row>
        </div>
      </Section>

      <RestTimerBar bottomOffset={54} />
    </Screen>
  )
}
