import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useLiveQuery } from 'dexie-react-hooks'
import { db } from '../db/db'
import type { SetLog, WorkoutSession } from '../db/types'
import { ConfirmDialog, NavHeader, Sheet, StatTile } from '../components/ui'
import { TrendChart, VolumeBarChart } from '../components/Charts'
import { PlateCalculator } from '../components/PlateCalculator'
import { ExerciseEditor } from './ExerciseLibrary'
import { useApp } from '../state/AppState'
import { epley1RM, kgToDisplay, setVolume, trimNum } from '../lib/calc'
import { formatDate, formatDateShort } from '../lib/format'
import { recomputePRs } from '../lib/pr'

type Metric = 'weight' | 'e1rm' | 'volume'

const METRIC_LABEL: Record<Metric, string> = {
  weight: 'Top-Gewicht',
  e1rm: 'Geschätztes 1RM',
  volume: 'Volumen',
}

export default function ExerciseDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { settings, pushToast } = useApp()
  const [metric, setMetric] = useState<Metric>('e1rm')
  const [editOpen, setEditOpen] = useState(false)
  const [plateOpen, setPlateOpen] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const data = useLiveQuery(async () => {
    if (!id) return null
    const exercise = await db.exercises.get(id)
    if (!exercise) return null
    const sets = await db.sets.where('exerciseId').equals(id).toArray()
    const sessionIds = [...new Set(sets.map((s) => s.sessionId))]
    const sessions = (await db.sessions.bulkGet(sessionIds)).filter(
      (s): s is WorkoutSession => !!s && !s.active,
    )
    const pr = await db.personalRecords.get(`pr_${id}`)
    return { exercise, sets: sets.filter((s) => s.done), sessions, pr }
  }, [id])

  const history = useMemo(() => {
    if (!data) return []
    const byId = new Map(data.sessions.map((s) => [s.id, s]))
    const grouped = new Map<string, { session: WorkoutSession; sets: SetLog[] }>()
    for (const s of data.sets) {
      const session = byId.get(s.sessionId)
      if (!session) continue
      const entry = grouped.get(session.id) ?? { session, sets: [] }
      entry.sets.push(s)
      grouped.set(session.id, entry)
    }
    return [...grouped.values()].sort((a, b) => a.session.startedAt - b.session.startedAt)
  }, [data])

  const chartData = useMemo(
    () =>
      history.map(({ session, sets }) => {
        const working = sets.filter((s) => s.type !== 'warmup')
        const value =
          metric === 'volume'
            ? working.reduce((a, s) => a + setVolume(s), 0)
            : metric === 'weight'
              ? Math.max(0, ...working.map((s) => s.weight))
              : Math.max(0, ...working.map((s) => epley1RM(s.weight, s.reps)))
        return { label: formatDateShort(session.date), value: kgToDisplay(value, settings.unit) }
      }),
    [history, metric, settings.unit],
  )

  if (data === undefined) return <div className="safe-top px-4 pt-10 text-center text-mute">Lädt…</div>
  if (data === null) {
    return (
      <div>
        <NavHeader title="Übung" onBack={() => navigate('/exercises')} />
        <p className="px-4 pt-8 text-center text-mute">Diese Übung gibt es nicht mehr.</p>
      </div>
    )
  }

  const { exercise, pr } = data
  const u = settings.unit
  const usedInWorkouts = history.length

  return (
    <div className="animate-page min-h-full">
      <NavHeader
        title={exercise.name}
        backLabel="Übungen"
        onBack={() => navigate(-1)}
        right={
          <button className="text-brand font-medium" onClick={() => setEditOpen(true)}>
            Bearbeiten
          </button>
        }
      />

      <div className="px-4 pb-tab">
        <div className="mt-2 flex flex-wrap gap-2">
          <span className="chip chip-active">{exercise.primary}</span>
          <span className="chip">{exercise.category}</span>
          {exercise.timeBased && <span className="chip">Zeitbasiert</span>}
          {exercise.secondary.map((m) => (
            <span key={m} className="chip">
              {m}
            </span>
          ))}
        </div>

        {exercise.instructions && (
          <div className="card mt-4 p-4">
            <div className="label mb-1.5">Ausführung</div>
            <p className="text-sm leading-relaxed text-white/85">{exercise.instructions}</p>
          </div>
        )}

        <div className="mt-4 grid grid-cols-2 gap-3">
          <StatTile
            label="Bestes Gewicht"
            value={pr?.bestWeight ? `${trimNum(kgToDisplay(pr.bestWeight, u), 1)} ${u}` : '—'}
            hint={pr?.bestWeightReps ? `${pr.bestWeightReps} Wdh.` : undefined}
          />
          <StatTile
            label="Bestes 1RM"
            value={pr?.bestE1rm ? `${trimNum(kgToDisplay(pr.bestE1rm, u), 1)} ${u}` : '—'}
            hint="Epley-Formel"
          />
          <StatTile
            label="Bestes Volumen"
            value={pr?.bestVolume ? `${trimNum(Math.round(kgToDisplay(pr.bestVolume, u)), 0)} ${u}` : '—'}
            hint="pro Workout"
          />
          <StatTile label="Einheiten" value={`${usedInWorkouts}`} hint="mit dieser Übung" />
        </div>

        <section className="mt-6">
          <div className="-mx-4 mb-2 flex gap-2 overflow-x-auto px-4 no-scrollbar">
            {(Object.keys(METRIC_LABEL) as Metric[]).map((m) => (
              <button
                key={m}
                className={`chip ${metric === m ? 'chip-active' : ''}`}
                onClick={() => setMetric(m)}
              >
                {METRIC_LABEL[m]}
              </button>
            ))}
          </div>
          <div className="card p-3 pt-4">
            {metric === 'volume' ? (
              <VolumeBarChart data={chartData} unit={u} />
            ) : (
              <TrendChart data={chartData} unit={u} name={METRIC_LABEL[metric]} />
            )}
          </div>
        </section>

        {exercise.category === 'Langhantel' && (
          <button className="btn-secondary mt-4 w-full" onClick={() => setPlateOpen(true)}>
            Hantelscheiben-Rechner
          </button>
        )}

        <section className="mt-6">
          <h2 className="label mb-2 px-1">Verlauf</h2>
          {history.length === 0 ? (
            <p className="card p-5 text-center text-sm text-mute">
              Noch nicht trainiert. Nimm die Übung in ein Workout auf.
            </p>
          ) : (
            <div className="card divide-y divide-ink-700 overflow-hidden">
              {[...history].reverse().slice(0, 25).map(({ session, sets }) => (
                <button
                  key={session.id}
                  className="w-full px-4 py-3 text-left active:bg-ink-800"
                  onClick={() => navigate(`/history/${session.id}`)}
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="truncate text-sm font-medium">{formatDate(session.date)}</span>
                    <span className="shrink-0 text-xs text-mute tnum">
                      {trimNum(Math.round(kgToDisplay(sets.reduce((a, s) => a + setVolume(s), 0), u)), 0)} {u}
                    </span>
                  </div>
                  <div className="mt-0.5 text-sm text-mute tnum">
                    {sets
                      .map((s) =>
                        exercise.timeBased
                          ? `${s.seconds ?? 0}s`
                          : `${trimNum(kgToDisplay(s.weight, u), 1)}×${s.reps}${s.type === 'warmup' ? ' (W)' : ''}`,
                      )
                      .join('  ·  ')}
                  </div>
                </button>
              ))}
            </div>
          )}
        </section>

        {exercise.custom && (
          <button className="btn-danger mt-6 w-full" onClick={() => setConfirmDelete(true)}>
            Übung löschen
          </button>
        )}
        {!exercise.custom && (
          <button
            className="btn-ghost mt-6 w-full"
            onClick={async () => {
              await db.exercises.update(exercise.id, { archived: true, updatedAt: Date.now() })
              pushToast({ kind: 'success', title: 'Übung ausgeblendet' })
              navigate('/exercises')
            }}
          >
            Aus der Liste ausblenden
          </button>
        )}
      </div>

      {editOpen && (
        <ExerciseEditor
          key={exercise.updatedAt}
          open={editOpen}
          existing={exercise}
          onClose={() => setEditOpen(false)}
          onSaved={() => pushToast({ kind: 'success', title: 'Gespeichert' })}
        />
      )}

      <Sheet open={plateOpen} onClose={() => setPlateOpen(false)} title="Hantelscheiben-Rechner">
        <PlateCalculator initialKg={pr?.bestWeight ?? 0} />
      </Sheet>

      <ConfirmDialog
        open={confirmDelete}
        title="Übung löschen?"
        message="Die Übung wird entfernt. Bereits protokollierte Sätze bleiben in den Workouts erhalten."
        onCancel={() => setConfirmDelete(false)}
        onConfirm={async () => {
          await db.exercises.delete(exercise.id)
          await recomputePRs([exercise.id])
          pushToast({ kind: 'success', title: 'Übung gelöscht' })
          navigate('/exercises', { replace: true })
        }}
      />
    </div>
  )
}
