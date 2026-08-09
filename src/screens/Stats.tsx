import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useLiveQuery } from 'dexie-react-hooks'
import { db } from '../db/db'
import type { Exercise, MuscleGroup, PRHistoryEntry, SetLog, WorkoutSession } from '../db/types'
import { MUSCLE_GROUPS } from '../db/types'
import { EmptyState, Screen, Section, StatTile } from '../components/ui'
import { DistributionBars, MUSCLE_COLORS, TrendChart, VolumeBarChart } from '../components/Charts'
import { useApp } from '../state/AppState'
import { computeWeekStreak } from '../lib/achievements'
import { computeRecovery, recoveryColor, recoveryLabel } from '../lib/recovery'
import { kgToDisplay, setVolume, trimNum } from '../lib/calc'
import { addDays, formatDateShort, formatDurationLong, startOfWeek, todayISO, weekKey } from '../lib/format'
import { PR_LABEL } from '../lib/pr'

type Range = 4 | 12 | 26 | 52

export default function Stats() {
  const navigate = useNavigate()
  const { settings } = useApp()
  const [range, setRange] = useState<Range>(12)

  const data = useLiveQuery(async () => {
    const [sessions, sets, exercises, prs] = await Promise.all([
      db.sessions.toArray(),
      db.sets.toArray(),
      db.exercises.toArray(),
      db.prHistory.toArray(),
    ])
    return {
      sessions: sessions.filter((s) => !s.active),
      sets: sets.filter((s) => s.done),
      exercises: new Map(exercises.map((e) => [e.id, e])),
      prs: prs.sort((a, b) => b.at - a.at),
    }
  }, [])

  const sessions = data?.sessions ?? []
  const sets = data?.sets ?? []
  const exercises = data?.exercises ?? new Map<string, Exercise>()
  const prs = data?.prs ?? []

  const activeSessionIds = useMemo(() => new Set(sessions.map((s) => s.id)), [sessions])
  const finishedSets = useMemo(() => sets.filter((s) => activeSessionIds.has(s.sessionId)), [sets, activeSessionIds])

  const weeks = useMemo(() => {
    const out: { key: string; label: string; volume: number; sets: number; workouts: number }[] = []
    const current = startOfWeek(new Date())
    const buckets = new Map<string, { volume: number; sets: number; workouts: number }>()
    const sessionById = new Map(sessions.map((s) => [s.id, s]))

    for (const s of sessions) {
      const k = weekKey(new Date(s.startedAt))
      const b = buckets.get(k) ?? { volume: 0, sets: 0, workouts: 0 }
      b.workouts += 1
      buckets.set(k, b)
    }
    for (const set of finishedSets) {
      const session = sessionById.get(set.sessionId)
      if (!session) continue
      const k = weekKey(new Date(session.startedAt))
      const b = buckets.get(k) ?? { volume: 0, sets: 0, workouts: 0 }
      b.volume += setVolume(set)
      b.sets += 1
      buckets.set(k, b)
    }

    for (let i = range - 1; i >= 0; i--) {
      const d = addDays(current, -7 * i)
      const k = todayISO(d)
      const b = buckets.get(k) ?? { volume: 0, sets: 0, workouts: 0 }
      out.push({ key: k, label: formatDateShort(k), ...b })
    }
    return out
  }, [sessions, finishedSets, range])

  const distribution = useMemo(() => {
    const counts = new Map<MuscleGroup, number>()
    for (const set of finishedSets) {
      const ex = exercises.get(set.exerciseId)
      if (!ex) continue
      counts.set(ex.primary, (counts.get(ex.primary) ?? 0) + 1)
      for (const m of ex.secondary) counts.set(m, (counts.get(m) ?? 0) + 0.5)
    }
    return MUSCLE_GROUPS.map((m) => ({
      label: m,
      value: counts.get(m) ?? 0,
      color: MUSCLE_COLORS[m] ?? '#71717a',
    }))
  }, [finishedSets, exercises])

  const recovery = useMemo(
    () => computeRecovery(sessions, finishedSets, exercises),
    [sessions, finishedSets, exercises],
  )

  const totals = useMemo(
    () => ({
      workouts: sessions.length,
      sets: finishedSets.length,
      volume: finishedSets.reduce((a, s) => a + setVolume(s), 0),
      time: sessions.reduce((a, s) => a + (s.durationSec ?? 0), 0),
      streak: computeWeekStreak(sessions),
      avgPerWeek:
        weeks.length > 0 ? weeks.reduce((a, w) => a + w.workouts, 0) / weeks.length : 0,
    }),
    [sessions, finishedSets, weeks],
  )

  const topExercises = useMemo(() => {
    const map = new Map<string, { sets: number; volume: number }>()
    for (const s of finishedSets) {
      const e = map.get(s.exerciseId) ?? { sets: 0, volume: 0 }
      e.sets += 1
      e.volume += setVolume(s)
      map.set(s.exerciseId, e)
    }
    return [...map.entries()]
      .map(([id, v]) => ({ id, name: exercises.get(id)?.name ?? 'Übung', ...v }))
      .sort((a, b) => b.sets - a.sets)
      .slice(0, 8)
  }, [finishedSets, exercises])

  const u = settings.unit

  if (data && sessions.length === 0) {
    return (
      <Screen title="Statistiken">
        <div className="mt-6">
          <EmptyState
            icon="📊"
            title="Noch keine Daten"
            message="Nach deinem ersten abgeschlossenen Workout erscheinen hier Diagramme zu Volumen, Muskelverteilung und Fortschritt."
          />
        </div>
      </Screen>
    )
  }

  return (
    <Screen title="Statistiken" subtitle={`${totals.workouts} Workouts insgesamt`}>
      <div className="-mx-4 mt-1 flex gap-2 overflow-x-auto px-4 no-scrollbar">
        {([4, 12, 26, 52] as Range[]).map((r) => (
          <button key={r} className={`chip ${range === r ? 'chip-active' : ''}`} onClick={() => setRange(r)}>
            {r} Wochen
          </button>
        ))}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <StatTile
          label="Gesamtvolumen"
          value={trimNum(Math.round(kgToDisplay(totals.volume, u)), 0)}
          hint={u}
        />
        <StatTile label="Sätze" value={`${totals.sets}`} />
        <StatTile label="Trainingszeit" value={formatDurationLong(totals.time)} />
        <StatTile
          label="Serie"
          value={`${totals.streak} Wo.`}
          hint={`Ø ${Math.round(totals.avgPerWeek * 10) / 10} Workouts/Woche`}
        />
      </div>

      <Section title="Volumen pro Woche">
        <div className="card p-3 pt-4">
          <VolumeBarChart
            data={weeks.map((w) => ({ label: w.label, value: kgToDisplay(w.volume, u) }))}
            unit={u}
          />
        </div>
      </Section>

      <Section title="Workouts pro Woche">
        <div className="card p-3 pt-4">
          <TrendChart
            data={weeks.map((w) => ({ label: w.label, value: w.workouts }))}
            color="#22c55e"
            name="Workouts"
            height={160}
          />
        </div>
      </Section>

      <Section title="Verteilung nach Muskelgruppe" className="mt-6">
        <div className="card p-4">
          <DistributionBars data={distribution} />
        </div>
      </Section>

      <Section title="Muskel-Erholung">
        <div className="card p-4">
          <div className="space-y-2.5">
            {recovery
              .slice()
              .sort((a, b) => a.recovery - b.recovery)
              .map((m) => (
                <div key={m.muscle} className="flex items-center gap-3">
                  <div className="w-24 shrink-0 truncate text-sm">{m.muscle}</div>
                  <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-ink-700">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{
                        width: `${Math.round(m.recovery * 100)}%`,
                        background: recoveryColor(m.recovery),
                      }}
                    />
                  </div>
                  <div className="w-24 shrink-0 text-right text-xs text-mute">{recoveryLabel(m.recovery)}</div>
                </div>
              ))}
          </div>
          <p className="mt-3 text-xs text-mute">
            Schätzung auf Basis der zuletzt trainierten Muskeln und der Zeit seitdem (48–72 Std. bis zur vollen
            Erholung).
          </p>
        </div>
      </Section>

      <Section title="Häufigste Übungen">
        <div className="card divide-y divide-ink-700 overflow-hidden">
          {topExercises.map((t) => (
            <button
              key={t.id}
              className="flex w-full items-center gap-3 px-4 py-3 text-left active:bg-ink-800"
              onClick={() => navigate(`/exercises/${t.id}`)}
            >
              <div className="min-w-0 flex-1 truncate">{t.name}</div>
              <div className="shrink-0 text-xs text-mute tnum">
                {t.sets} Sätze · {trimNum(Math.round(kgToDisplay(t.volume, u)), 0)} {u}
              </div>
              <span className="text-mute">›</span>
            </button>
          ))}
        </div>
      </Section>

      <Section
        title="Rekord-Verlauf"
        action={
          <button className="text-sm text-brand font-medium" onClick={() => navigate('/achievements')}>
            Erfolge
          </button>
        }
      >
        {prs.length === 0 ? (
          <p className="card p-5 text-center text-sm text-mute">Noch keine persönlichen Rekorde erfasst.</p>
        ) : (
          <div className="card divide-y divide-ink-700 overflow-hidden">
            {prs.slice(0, 15).map((pr: PRHistoryEntry) => (
              <button
                key={pr.id}
                className="flex w-full items-center gap-3 px-4 py-3 text-left active:bg-ink-800"
                onClick={() => navigate(`/exercises/${pr.exerciseId}`)}
              >
                <span className="text-base">🏆</span>
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{exercises.get(pr.exerciseId)?.name ?? 'Übung'}</div>
                  <div className="text-xs text-mute">
                    {PR_LABEL[pr.kind]} · {new Date(pr.at).toLocaleDateString('de-DE')}
                  </div>
                </div>
                <div className="shrink-0 text-sm font-semibold tnum">
                  {pr.kind === 'reps'
                    ? `${Math.round(pr.value)} Wdh.`
                    : `${trimNum(kgToDisplay(pr.value, u), 1)} ${u}`}
                </div>
              </button>
            ))}
          </div>
        )}
      </Section>

      <Section title="Konsistenz">
        <ConsistencyGrid sessions={sessions} />
      </Section>
    </Screen>
  )
}

/** Kalender-Heatmap der letzten 16 Wochen. */
function ConsistencyGrid({ sessions }: { sessions: WorkoutSession[] }) {
  const days = useMemo(() => {
    const counts = new Map<string, number>()
    for (const s of sessions) counts.set(s.date, (counts.get(s.date) ?? 0) + 1)
    const start = addDays(startOfWeek(new Date()), -7 * 15)
    return Array.from({ length: 16 * 7 }, (_, i) => {
      const d = addDays(start, i)
      const iso = todayISO(d)
      return { iso, count: counts.get(iso) ?? 0, future: d.getTime() > Date.now() }
    })
  }, [sessions])

  return (
    <div className="card p-4">
      <div className="grid grid-flow-col grid-rows-7 gap-[3px]" style={{ gridAutoColumns: '1fr' }}>
        {days.map((d) => (
          <div
            key={d.iso}
            title={`${d.iso}: ${d.count} Workout(s)`}
            className="aspect-square rounded-[3px]"
            style={{
              background: d.future
                ? 'transparent'
                : d.count === 0
                  ? '#1d1d20'
                  : d.count === 1
                    ? '#16a34a'
                    : '#4ade80',
            }}
          />
        ))}
      </div>
      <p className="mt-3 text-xs text-mute">Letzte 16 Wochen — jede Spalte ist eine Woche (Mo–So).</p>
    </div>
  )
}

export type { SetLog }
