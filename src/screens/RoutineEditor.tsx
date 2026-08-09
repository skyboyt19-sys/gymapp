import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useLiveQuery } from 'dexie-react-hooks'
import { db } from '../db/db'
import type { Exercise, RoutineExercise } from '../db/types'
import { ConfirmDialog, EmptyState, NavHeader, Stepper } from '../components/ui'
import { ExercisePicker } from '../components/ExercisePicker'
import { DragHandle, SortableList } from '../components/SortableList'
import { useWorkout } from '../state/WorkoutState'
import { useApp } from '../state/AppState'
import { haptic } from '../lib/feedback'

export default function RoutineEditor() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { session, startWorkout } = useWorkout()
  const { pushToast } = useApp()
  const [pickerOpen, setPickerOpen] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const data = useLiveQuery(async () => {
    if (!id) return null
    const routine = await db.routines.get(id)
    if (!routine) return null
    const exercises = new Map((await db.exercises.toArray()).map((e) => [e.id, e]))
    return { routine, exercises }
  }, [id])

  if (data === undefined) return <div className="safe-top px-4 pt-10 text-center text-mute">Lädt…</div>
  if (data === null) {
    return (
      <div>
        <NavHeader title="Routine" onBack={() => navigate('/routines')} />
        <p className="px-4 pt-8 text-center text-mute">Diese Routine gibt es nicht mehr.</p>
      </div>
    )
  }

  const { routine, exercises } = data

  const save = (patch: Partial<typeof routine>) =>
    db.routines.update(routine.id, { ...patch, updatedAt: Date.now() })

  const updateExercise = (index: number, patch: Partial<RoutineExercise>) => {
    const next = routine.exercises.map((e, i) => (i === index ? { ...e, ...patch } : e))
    return save({ exercises: next })
  }

  const removeExercise = (index: number) =>
    save({ exercises: routine.exercises.filter((_, i) => i !== index) })

  const ids = routine.exercises.map((e) => e.exerciseId)

  return (
    <div className="animate-page min-h-full">
      <NavHeader
        title="Routine"
        backLabel="Routinen"
        onBack={() => navigate('/routines')}
        right={
          <button
            className="text-brand font-medium disabled:opacity-40"
            disabled={!!session || routine.exercises.length === 0}
            onClick={async () => {
              haptic('success')
              await startWorkout({ routineId: routine.id })
              navigate('/workout')
            }}
          >
            Starten
          </button>
        }
      />

      <div className="px-4 pb-tab">
        <input
          className="field mt-2 text-lg font-semibold"
          value={routine.name}
          onChange={(e) => void save({ name: e.target.value })}
          placeholder="Name der Routine"
        />
        <textarea
          className="field mt-3 min-h-16"
          value={routine.notes ?? ''}
          onChange={(e) => void save({ notes: e.target.value })}
          placeholder="Notiz (optional)"
        />

        {routine.exercises.length === 0 ? (
          <div className="mt-6">
            <EmptyState
              icon="➕"
              title="Noch keine Übungen"
              message="Füge Übungen hinzu und lege Ziel-Sätze und -Wiederholungen fest."
              action={
                <button className="btn-primary" onClick={() => setPickerOpen(true)}>
                  Übungen hinzufügen
                </button>
              }
            />
          </div>
        ) : (
          <div className="mt-4">
            <SortableList
              items={ids}
              onReorder={(next) => {
                const map = new Map(routine.exercises.map((e) => [e.exerciseId, e]))
                void save({ exercises: next.map((exId) => map.get(exId)!).filter(Boolean) })
              }}
              renderItem={(exId, index, handleProps) => {
                const ex: Exercise | undefined = exercises.get(exId)
                const re = routine.exercises[index]
                if (!ex || !re) return null
                return (
                  <div className="card mb-3 overflow-hidden">
                    <div className="flex items-center gap-1 border-b border-ink-700 px-2 py-2">
                      <DragHandle handleProps={handleProps} />
                      <div className="min-w-0 flex-1">
                        <div className="truncate font-semibold">{ex.name}</div>
                        <div className="truncate text-xs text-mute">
                          {ex.primary} · {ex.category}
                        </div>
                      </div>
                      <button
                        className="px-3 py-2 text-sm text-red-400"
                        onClick={() => void removeExercise(index)}
                      >
                        Entfernen
                      </button>
                    </div>
                    <div className="grid grid-cols-2 gap-3 p-3">
                      <Stepper
                        label="Sätze"
                        value={re.targetSets}
                        min={1}
                        max={20}
                        onChange={(v) => void updateExercise(index, { targetSets: v })}
                      />
                      {ex.timeBased ? (
                        <Stepper
                          label="Dauer"
                          value={re.targetSeconds ?? 60}
                          step={15}
                          min={5}
                          max={3600}
                          suffix="s"
                          onChange={(v) => void updateExercise(index, { targetSeconds: v })}
                        />
                      ) : (
                        <Stepper
                          label="Wdh."
                          value={re.targetReps}
                          min={1}
                          max={100}
                          onChange={(v) => void updateExercise(index, { targetReps: v })}
                        />
                      )}
                    </div>
                  </div>
                )
              }}
            />
          </div>
        )}

        <div className="mt-4 space-y-2.5">
          <button className="btn-secondary w-full" onClick={() => setPickerOpen(true)}>
            + Übung hinzufügen
          </button>
          <button className="btn-danger w-full" onClick={() => setConfirmDelete(true)}>
            Routine löschen
          </button>
        </div>
        <p className="mt-4 text-center text-xs text-mute">
          Änderungen werden automatisch gespeichert. Zum Sortieren den Griff links gedrückt halten.
        </p>
      </div>

      <ExercisePicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        excludeIds={ids}
        onPick={async (picked) => {
          const additions: RoutineExercise[] = []
          for (const exId of picked) {
            const ex = exercises.get(exId)
            additions.push({
              exerciseId: exId,
              targetSets: 3,
              targetReps: ex?.timeBased ? 0 : 10,
              targetSeconds: ex?.timeBased ? 60 : undefined,
              restSec: ex?.restSec,
            })
          }
          await save({ exercises: [...routine.exercises, ...additions] })
        }}
      />

      <ConfirmDialog
        open={confirmDelete}
        title="Routine löschen?"
        message="Bereits absolvierte Workouts bleiben im Verlauf erhalten."
        onCancel={() => setConfirmDelete(false)}
        onConfirm={async () => {
          await db.routines.delete(routine.id)
          pushToast({ kind: 'success', title: 'Routine gelöscht' })
          navigate('/routines', { replace: true })
        }}
      />
    </div>
  )
}
