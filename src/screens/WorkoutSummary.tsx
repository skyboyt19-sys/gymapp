import { useNavigate, useParams } from 'react-router-dom'
import { useLiveQuery } from 'dexie-react-hooks'
import { db } from '../db/db'
import { StatTile } from '../components/ui'
import { useApp } from '../state/AppState'
import { epley1RM, kgToDisplay, trimNum } from '../lib/calc'
import { formatDurationLong } from '../lib/format'
import { PR_LABEL } from '../lib/pr'
import { ACHIEVEMENTS } from '../lib/achievements'

export default function WorkoutSummary() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { settings } = useApp()

  const data = useLiveQuery(async () => {
    if (!id) return null
    const session = await db.sessions.get(id)
    if (!session) return null
    const sets = await db.sets.where('sessionId').equals(id).toArray()
    const exercises = new Map((await db.exercises.toArray()).map((e) => [e.id, e]))
    const prs = (await db.prHistory.where('sessionId').equals(id).toArray()).sort((a, b) => b.value - a.value)
    // Erfolge, die rund um dieses Workout freigeschaltet wurden
    const unlocked = (await db.achievements.toArray()).filter(
      (a) => Math.abs(a.unlockedAt - (session.endedAt ?? session.startedAt)) < 60_000,
    )
    return { session, sets, exercises, prs, unlocked }
  }, [id])

  if (!data) {
    return (
      <div className="safe-top px-4 pt-10 text-center text-mute">
        Zusammenfassung wird geladen…
      </div>
    )
  }

  const { session, sets, exercises, prs, unlocked } = data
  const volume = session.totalVolume ?? 0
  const byExercise = session.exerciseOrder.length
    ? session.exerciseOrder
    : [...new Set(sets.map((s) => s.exerciseId))]

  return (
    <div className="animate-page min-h-full">
      <div className="safe-top px-4 pb-tab">
        <div className="pt-6 text-center">
          <div className="text-5xl">🎉</div>
          <h1 className="mt-3 text-2xl font-bold">Workout beendet</h1>
          <p className="mt-1 text-mute">{session.name}</p>
        </div>

        <div className="mt-6 grid grid-cols-2 gap-3">
          <StatTile label="Dauer" value={formatDurationLong(session.durationSec ?? 0)} />
          <StatTile label="Sätze" value={`${session.totalSets ?? sets.length}`} />
          <StatTile
            label="Volumen"
            value={`${trimNum(Math.round(kgToDisplay(volume, settings.unit)), 0)} ${settings.unit}`}
          />
          <StatTile label="Übungen" value={`${byExercise.length}`} />
        </div>

        {prs.length > 0 && (
          <section className="mt-6">
            <h2 className="label mb-2 px-1">Neue Rekorde</h2>
            <div className="card divide-y divide-ink-700 overflow-hidden">
              {prs.map((pr) => {
                const ex = exercises.get(pr.exerciseId)
                const value =
                  pr.kind === 'reps'
                    ? `${Math.round(pr.value)} Wdh.`
                    : `${trimNum(kgToDisplay(pr.value, settings.unit), 1)} ${settings.unit}`
                return (
                  <div key={pr.id} className="flex items-center gap-3 px-4 py-3">
                    <span className="text-xl">🏆</span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-medium">{ex?.name ?? 'Übung'}</div>
                      <div className="text-xs text-mute">{PR_LABEL[pr.kind]}</div>
                    </div>
                    <div className="font-semibold tnum">{value}</div>
                  </div>
                )
              })}
            </div>
          </section>
        )}

        {unlocked.length > 0 && (
          <section className="mt-6">
            <h2 className="label mb-2 px-1">Erfolge freigeschaltet</h2>
            <div className="card divide-y divide-ink-700 overflow-hidden">
              {unlocked.map((a) => {
                const def = ACHIEVEMENTS.find((d) => d.key === a.key)
                return (
                  <div key={a.id} className="flex items-center gap-3 px-4 py-3">
                    <span className="text-xl">{def?.icon ?? '🎖️'}</span>
                    <div className="min-w-0">
                      <div className="font-medium">{def?.title ?? a.key}</div>
                      <div className="text-xs text-mute">{def?.description}</div>
                    </div>
                  </div>
                )
              })}
            </div>
          </section>
        )}

        <section className="mt-6">
          <h2 className="label mb-2 px-1">Übungen</h2>
          <div className="card divide-y divide-ink-700 overflow-hidden">
            {byExercise.map((exId) => {
              const ex = exercises.get(exId)
              const exSets = sets.filter((s) => s.exerciseId === exId)
              if (exSets.length === 0) return null
              const best = exSets.reduce(
                (acc, s) => Math.max(acc, epley1RM(s.weight, s.reps)),
                0,
              )
              return (
                <div key={exId} className="px-4 py-3">
                  <div className="flex items-baseline justify-between gap-3">
                    <div className="min-w-0 truncate font-medium">{ex?.name ?? 'Übung'}</div>
                    <div className="shrink-0 text-xs text-mute tnum">
                      {exSets.length} {exSets.length === 1 ? 'Satz' : 'Sätze'}
                    </div>
                  </div>
                  <div className="mt-1 text-sm text-mute tnum">
                    {exSets
                      .map((s) =>
                        ex?.timeBased
                          ? `${s.seconds ?? 0}s`
                          : `${trimNum(kgToDisplay(s.weight, settings.unit), 1)}×${s.reps}`,
                      )
                      .join('  ·  ')}
                  </div>
                  {best > 0 && (
                    <div className="mt-1 text-xs text-mute">
                      Bestes geschätztes 1RM: {trimNum(kgToDisplay(best, settings.unit), 1)} {settings.unit}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </section>

        <div className="mt-6 space-y-2.5">
          <button className="btn-primary w-full" onClick={() => navigate('/', { replace: true })}>
            Fertig
          </button>
          <button
            className="btn-secondary w-full"
            onClick={() => navigate(`/history/${session.id}`, { replace: true })}
          >
            Workout bearbeiten
          </button>
        </div>
      </div>
    </div>
  )
}
