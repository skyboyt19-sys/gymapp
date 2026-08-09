import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useLiveQuery } from 'dexie-react-hooks'
import { db } from '../db/db'
import type { Exercise, SetLog } from '../db/types'
import { ConfirmDialog, EmptyState, Sheet, Stepper } from '../components/ui'
import { ExercisePicker } from '../components/ExercisePicker'
import { RestTimerBar } from '../components/RestTimerBar'
import { SetHeader, SetRow } from '../components/SetRows'
import { DragHandle, SortableList } from '../components/SortableList'
import { PlateCalculator } from '../components/PlateCalculator'
import { lastSetsFor, useWorkout } from '../state/WorkoutState'
import { useApp } from '../state/AppState'
import { formatDuration } from '../lib/format'
import { kgToDisplay, setVolume, trimNum } from '../lib/calc'
import { haptic } from '../lib/feedback'

const RPE_KEY = 'lift.showRpe'

export default function ActiveWorkout() {
  const navigate = useNavigate()
  const { settings } = useApp()
  const {
    session,
    sets,
    startRest,
    addExercise,
    removeExercise,
    reorderExercises,
    addSet,
    updateSet,
    removeSet,
    toggleSetDone,
    finishWorkout,
    discardWorkout,
    updateSessionNotes,
    renameSession,
  } = useWorkout()

  const [pickerOpen, setPickerOpen] = useState(false)
  const [confirmDiscard, setConfirmDiscard] = useState(false)
  const [confirmFinish, setConfirmFinish] = useState(false)
  const [notesOpen, setNotesOpen] = useState(false)
  const [menuFor, setMenuFor] = useState<string | null>(null)
  const [plateFor, setPlateFor] = useState<number | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const [showRpe, setShowRpe] = useState(() => localStorage.getItem(RPE_KEY) === '1')
  const [finishing, setFinishing] = useState(false)

  const exercises = useLiveQuery(
    async () => new Map((await db.exercises.toArray()).map((e) => [e.id, e])),
    [],
    new Map<string, Exercise>(),
  )

  const order = session?.exerciseOrder ?? []

  // Vorschläge aus dem jeweils letzten Workout
  const previous = useLiveQuery(async () => {
    const map = new Map<string, SetLog[]>()
    for (const id of order) map.set(id, await lastSetsFor(id))
    return map
  }, [order.join(',')], new Map<string, SetLog[]>())

  useEffect(() => {
    if (!session) return
    const tick = () => setElapsed(Math.floor((Date.now() - session.startedAt) / 1000))
    tick()
    const t = setInterval(tick, 1000)
    return () => clearInterval(t)
  }, [session])

  useEffect(() => {
    localStorage.setItem(RPE_KEY, showRpe ? '1' : '0')
  }, [showRpe])

  const stats = useMemo(() => {
    const done = sets.filter((s) => s.done)
    return {
      sets: done.length,
      volume: done.reduce((a, s) => a + setVolume(s), 0),
      total: sets.length,
    }
  }, [sets])

  if (!session) {
    return (
      <div className="safe-top px-4">
        <EmptyState
          icon="🏋️"
          title="Kein aktives Workout"
          message="Starte ein Workout auf der Startseite."
          action={
            <button className="btn-primary" onClick={() => navigate('/')}>
              Zur Startseite
            </button>
          }
        />
      </div>
    )
  }

  const finish = async () => {
    if (finishing) return
    setFinishing(true)
    const id = session.id
    try {
      const summary = await finishWorkout()
      setConfirmFinish(false)
      if (summary) navigate(`/summary/${id}`, { replace: true })
      else navigate('/', { replace: true })
    } finally {
      setFinishing(false)
    }
  }

  return (
    <div className="animate-page min-h-full">
      <header className="safe-top sticky top-0 z-30 bg-black/90 px-4 pb-3 backdrop-blur-xl">
        <div className="flex items-center gap-3">
          <button className="text-brand font-medium py-1" onClick={() => navigate('/')}>
            ‹ Start
          </button>
          <div className="min-w-0 flex-1 text-center">
            <div className="truncate text-[15px] font-semibold">{session.name}</div>
            <div className="text-xs text-mute tnum">{formatDuration(elapsed)}</div>
          </div>
          <button className="btn-primary px-3 text-sm" onClick={() => setConfirmFinish(true)}>
            Beenden
          </button>
        </div>

        <div className="mt-2.5 flex items-center gap-2 text-xs text-mute">
          <span className="tnum">
            {stats.sets}/{stats.total} Sätze
          </span>
          <span>·</span>
          <span className="tnum">
            {trimNum(Math.round(kgToDisplay(stats.volume, settings.unit)), 0)} {settings.unit} Volumen
          </span>
          <button
            className={`ml-auto chip py-1 text-xs ${showRpe ? 'chip-active' : ''}`}
            onClick={() => setShowRpe((v) => !v)}
          >
            RPE
          </button>
        </div>
      </header>

      <div className="px-3" style={{ paddingBottom: 'calc(var(--safe-bottom) + 150px)' }}>
        {order.length === 0 && (
          <div className="mt-6">
            <EmptyState
              icon="➕"
              title="Noch keine Übung"
              message="Füge Übungen hinzu, um mit dem Loggen zu starten."
              action={
                <button className="btn-primary" onClick={() => setPickerOpen(true)}>
                  Übung hinzufügen
                </button>
              }
            />
          </div>
        )}

        <SortableList
          items={order}
          onReorder={(next) => void reorderExercises(next)}
          renderItem={(exerciseId, _index, handleProps) => {
            const ex = exercises.get(exerciseId)
            if (!ex) return null
            const exSets = sets.filter((s) => s.exerciseId === exerciseId)
            const prev = previous.get(exerciseId) ?? []
            return (
              <div className="card mt-3 overflow-hidden">
                <div className="flex items-center gap-1 border-b border-ink-700 px-2 py-2">
                  <DragHandle handleProps={handleProps} />
                  <button
                    className="min-w-0 flex-1 text-left"
                    onClick={() => navigate(`/exercises/${ex.id}`)}
                  >
                    <div className="truncate font-semibold">{ex.name}</div>
                    <div className="truncate text-xs text-mute">
                      {ex.primary} · Pause {ex.restSec}s
                    </div>
                  </button>
                  <button
                    className="px-2 py-2 text-xl leading-none text-mute"
                    aria-label="Übungsoptionen"
                    onClick={() => setMenuFor(exerciseId)}
                  >
                    ⋯
                  </button>
                </div>

                <SetHeader timeBased={ex.timeBased} unit={settings.unit} showRpe={showRpe} />

                {exSets.map((s, i) => (
                  <SetRow
                    key={s.id}
                    set={s}
                    exercise={ex}
                    unit={settings.unit}
                    previous={prev[i]}
                    showRpe={showRpe}
                    onUpdate={(patch) => void updateSet(s.id, patch)}
                    onToggleDone={() => void toggleSetDone(s.id)}
                    onDelete={() => void removeSet(s.id)}
                  />
                ))}

                <div className="flex gap-2 px-2 py-2">
                  <button
                    className="btn-secondary flex-1 text-sm"
                    onClick={() => {
                      haptic()
                      void addSet(exerciseId)
                    }}
                  >
                    + Satz
                  </button>
                  {!ex.timeBased && ex.category === 'Langhantel' && (
                    <button
                      className="btn-secondary px-3 text-sm"
                      onClick={() => setPlateFor(exSets[exSets.length - 1]?.weight ?? 0)}
                    >
                      Scheiben
                    </button>
                  )}
                  <button
                    className="btn-secondary px-3 text-sm"
                    onClick={() => {
                      haptic()
                      startRest(ex.restSec || settings.defaultRestSec, ex.id)
                    }}
                  >
                    Pause
                  </button>
                </div>
              </div>
            )
          }}
        />

        <div className="mt-4 space-y-2.5">
          <button className="btn-secondary w-full" onClick={() => setPickerOpen(true)}>
            + Übung hinzufügen
          </button>
          <button className="btn-ghost w-full" onClick={() => setNotesOpen(true)}>
            {session.notes ? 'Notiz bearbeiten' : 'Notiz hinzufügen'}
          </button>
          <button className="btn-ghost w-full text-red-400" onClick={() => setConfirmDiscard(true)}>
            Workout verwerfen
          </button>
        </div>
      </div>

      <RestTimerBar />

      <ExercisePicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        excludeIds={order}
        onPick={(ids) => void addExercise(ids)}
      />

      <Sheet open={!!menuFor} onClose={() => setMenuFor(null)} title="Übung">
        {menuFor && (
          <div className="space-y-2">
            <button
              className="w-full rounded-xl bg-ink-800 px-4 py-3 text-left"
              onClick={() => {
                const id = menuFor
                setMenuFor(null)
                navigate(`/exercises/${id}`)
              }}
            >
              Übung ansehen / bearbeiten
            </button>
            <PauseStepper exerciseId={menuFor} />
            <button
              className="btn-danger mt-3 w-full"
              onClick={() => {
                void removeExercise(menuFor)
                setMenuFor(null)
              }}
            >
              Übung aus Workout entfernen
            </button>
          </div>
        )}
      </Sheet>

      <Sheet
        open={notesOpen}
        onClose={() => setNotesOpen(false)}
        title="Workout"
        footer={
          <button className="btn-primary w-full" onClick={() => setNotesOpen(false)}>
            Speichern
          </button>
        }
      >
        <label className="label mb-1.5 block">Name</label>
        <input
          className="field mb-4"
          value={session.name}
          onChange={(e) => void renameSession(e.target.value)}
          placeholder="Workout-Name"
        />
        <label className="label mb-1.5 block">Notizen</label>
        <textarea
          className="field min-h-32"
          value={session.notes ?? ''}
          onChange={(e) => void updateSessionNotes(e.target.value)}
          placeholder="Wie lief es? Was ist aufgefallen?"
        />
      </Sheet>

      <Sheet open={plateFor !== null} onClose={() => setPlateFor(null)} title="Hantelscheiben-Rechner">
        <PlateCalculator initialKg={plateFor ?? 0} />
      </Sheet>

      <ConfirmDialog
        open={confirmDiscard}
        title="Workout verwerfen?"
        message="Alle Sätze dieses Workouts werden gelöscht. Das lässt sich nicht rückgängig machen."
        confirmLabel="Verwerfen"
        onCancel={() => setConfirmDiscard(false)}
        onConfirm={async () => {
          await discardWorkout()
          setConfirmDiscard(false)
          navigate('/', { replace: true })
        }}
      />

      <ConfirmDialog
        open={confirmFinish}
        title="Workout beenden?"
        message={
          stats.sets === 0
            ? 'Es ist noch kein Satz abgehakt — das Workout wird dann verworfen.'
            : `${stats.sets} Sätze werden gespeichert. Nicht abgehakte Sätze werden verworfen.`
        }
        confirmLabel="Beenden"
        destructive={stats.sets === 0}
        onCancel={() => setConfirmFinish(false)}
        onConfirm={finish}
      />
    </div>
  )
}

/** Pausenzeit dieser Übung dauerhaft ändern. */
function PauseStepper({ exerciseId }: { exerciseId: string }) {
  const ex = useLiveQuery(() => db.exercises.get(exerciseId), [exerciseId])
  if (!ex) return null
  return (
    <div className="rounded-xl bg-ink-800 px-4 py-3">
      <Stepper
        label="Pausenzeit für diese Übung"
        value={ex.restSec}
        step={15}
        min={0}
        max={600}
        suffix="Sek"
        onChange={(v) => void db.exercises.update(exerciseId, { restSec: v, updatedAt: Date.now() })}
      />
    </div>
  )
}
