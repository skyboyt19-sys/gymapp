import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useLiveQuery } from 'dexie-react-hooks'
import { db, uid } from '../db/db'
import type { Exercise, SetLog } from '../db/types'
import { ConfirmDialog, NavHeader, Sheet, StatTile } from '../components/ui'
import { ExercisePicker } from '../components/ExercisePicker'
import { SetHeader, SetRow } from '../components/SetRows'
import { useApp } from '../state/AppState'
import { kgToDisplay, trimNum } from '../lib/calc'
import { formatDate, formatDurationLong, formatTime } from '../lib/format'
import { deleteSession, recalcSession } from '../lib/session'
import { haptic } from '../lib/feedback'

export default function SessionDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { settings, pushToast } = useApp()
  const [editOpen, setEditOpen] = useState(false)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [removeExercise, setRemoveExercise] = useState<string | null>(null)

  const data = useLiveQuery(async () => {
    if (!id) return null
    const session = await db.sessions.get(id)
    if (!session) return null
    const sets = (await db.sets.where('sessionId').equals(id).toArray()).sort(
      (a, b) => a.createdAt - b.createdAt,
    )
    const exercises = new Map((await db.exercises.toArray()).map((e) => [e.id, e]))
    return { session, sets, exercises }
  }, [id])

  if (data === undefined) return <div className="safe-top px-4 pt-10 text-center text-mute">Lädt…</div>
  if (data === null) {
    return (
      <div>
        <NavHeader title="Workout" onBack={() => navigate('/history')} />
        <p className="px-4 pt-8 text-center text-mute">Dieses Workout gibt es nicht mehr.</p>
      </div>
    )
  }

  const { session, sets, exercises } = data
  const order = session.exerciseOrder.length
    ? session.exerciseOrder
    : [...new Set(sets.map((s) => s.exerciseId))]

  const update = async (fn: () => Promise<unknown>) => {
    await fn()
    await recalcSession(session.id)
  }

  const addSet = async (exerciseId: string) => {
    const exSets = sets.filter((s) => s.exerciseId === exerciseId)
    const last = exSets[exSets.length - 1]
    await update(() =>
      db.sets.add({
        id: uid('set'),
        sessionId: session.id,
        exerciseId,
        setNumber: exSets.length + 1,
        weight: last?.weight ?? 0,
        reps: last?.reps ?? 10,
        seconds: last?.seconds,
        type: 'normal',
        done: true,
        createdAt: (last?.createdAt ?? session.startedAt) + 1,
      } satisfies SetLog),
    )
  }

  return (
    <div className="animate-page min-h-full">
      <NavHeader
        title={formatDate(session.date)}
        backLabel="Verlauf"
        onBack={() => navigate('/history')}
        right={
          <button className="text-brand font-medium" onClick={() => setEditOpen(true)}>
            Bearbeiten
          </button>
        }
      />

      <div className="px-4 pb-tab">
        <h1 className="mt-2 text-2xl font-bold">{session.name}</h1>
        <p className="mt-1 text-sm text-mute">
          {formatTime(session.startedAt)}
          {session.endedAt ? `–${formatTime(session.endedAt)}` : ''} Uhr
          {session.routineName ? ` · ${session.routineName}` : ''}
        </p>

        <div className="mt-4 grid grid-cols-3 gap-3">
          <StatTile label="Dauer" value={formatDurationLong(session.durationSec ?? 0)} />
          <StatTile label="Sätze" value={`${session.totalSets ?? 0}`} />
          <StatTile
            label="Volumen"
            value={trimNum(Math.round(kgToDisplay(session.totalVolume ?? 0, settings.unit)), 0)}
            hint={settings.unit}
          />
        </div>

        {session.notes && (
          <div className="card mt-4 p-4">
            <div className="label mb-1">Notiz</div>
            <p className="whitespace-pre-wrap text-sm leading-relaxed">{session.notes}</p>
          </div>
        )}

        {order.map((exId) => {
          const ex = exercises.get(exId)
          if (!ex) return null
          const exSets = sets.filter((s) => s.exerciseId === exId)
          return (
            <div key={exId} className="card mt-4 overflow-hidden">
              <div className="flex items-center gap-2 border-b border-ink-700 px-3 py-2.5">
                <button className="min-w-0 flex-1 text-left" onClick={() => navigate(`/exercises/${exId}`)}>
                  <div className="truncate font-semibold">{ex.name}</div>
                  <div className="text-xs text-mute">{ex.primary}</div>
                </button>
                <button
                  className="px-2 py-1 text-sm text-red-400"
                  onClick={() => setRemoveExercise(exId)}
                >
                  Entfernen
                </button>
              </div>

              <SetHeader timeBased={ex.timeBased} unit={settings.unit} showRpe />

              {exSets.map((s) => (
                <SetRow
                  key={s.id}
                  set={s}
                  exercise={ex}
                  unit={settings.unit}
                  showRpe
                  onUpdate={(patch) => void update(() => db.sets.update(s.id, patch))}
                  onToggleDone={() => void update(() => db.sets.update(s.id, { done: !s.done }))}
                  onDelete={() => void update(() => db.sets.delete(s.id))}
                />
              ))}

              <div className="px-2 py-2">
                <button className="btn-secondary w-full text-sm" onClick={() => void addSet(exId)}>
                  + Satz
                </button>
              </div>
            </div>
          )
        })}

        <div className="mt-5 space-y-2.5">
          <button className="btn-secondary w-full" onClick={() => setPickerOpen(true)}>
            + Übung hinzufügen
          </button>
          <button className="btn-danger w-full" onClick={() => setConfirmDelete(true)}>
            Workout löschen
          </button>
        </div>
      </div>

      <ExercisePicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        excludeIds={order}
        onPick={async (ids) => {
          for (const exId of ids) {
            const ex: Exercise | undefined = exercises.get(exId)
            await db.sets.add({
              id: uid('set'),
              sessionId: session.id,
              exerciseId: exId,
              setNumber: 1,
              weight: 0,
              reps: ex?.timeBased ? 0 : 10,
              seconds: ex?.timeBased ? 60 : undefined,
              type: 'normal',
              done: true,
              createdAt: Date.now(),
            })
          }
          await db.sessions.update(session.id, { exerciseOrder: [...order, ...ids] })
          await recalcSession(session.id)
        }}
      />

      <Sheet
        open={editOpen}
        onClose={() => setEditOpen(false)}
        title="Workout bearbeiten"
        footer={
          <button className="btn-primary w-full" onClick={() => setEditOpen(false)}>
            Fertig
          </button>
        }
      >
        <label className="label mb-1.5 block">Name</label>
        <input
          className="field mb-4"
          value={session.name}
          onChange={(e) => void db.sessions.update(session.id, { name: e.target.value })}
        />

        <label className="label mb-1.5 block">Datum</label>
        <input
          type="date"
          className="field mb-4"
          value={session.date}
          onChange={(e) => {
            const iso = e.target.value
            if (!iso) return
            const [y, m, d] = iso.split('-').map(Number)
            const start = new Date(session.startedAt)
            start.setFullYear(y, m - 1, d)
            const shift = start.getTime() - session.startedAt
            void db.sessions.update(session.id, {
              date: iso,
              startedAt: start.getTime(),
              endedAt: session.endedAt ? session.endedAt + shift : undefined,
            })
          }}
        />

        <label className="label mb-1.5 block">Dauer (Minuten)</label>
        <input
          type="number"
          inputMode="numeric"
          className="field mb-4"
          value={Math.round((session.durationSec ?? 0) / 60)}
          onChange={(e) => {
            const min = Math.max(0, Number(e.target.value) || 0)
            void db.sessions.update(session.id, {
              durationSec: min * 60,
              endedAt: session.startedAt + min * 60_000,
            })
          }}
        />

        <label className="label mb-1.5 block">Notizen</label>
        <textarea
          className="field min-h-28"
          value={session.notes ?? ''}
          onChange={(e) => void db.sessions.update(session.id, { notes: e.target.value })}
        />
      </Sheet>

      <ConfirmDialog
        open={!!removeExercise}
        title="Übung entfernen?"
        message="Alle Sätze dieser Übung in diesem Workout werden gelöscht."
        confirmLabel="Entfernen"
        onCancel={() => setRemoveExercise(null)}
        onConfirm={async () => {
          const exId = removeExercise!
          setRemoveExercise(null)
          await db.sets.where({ sessionId: session.id, exerciseId: exId }).delete()
          await db.sessions.update(session.id, {
            exerciseOrder: order.filter((x) => x !== exId),
          })
          await recalcSession(session.id)
        }}
      />

      <ConfirmDialog
        open={confirmDelete}
        title="Workout löschen?"
        message="Das Workout und alle zugehörigen Sätze werden dauerhaft entfernt."
        onCancel={() => setConfirmDelete(false)}
        onConfirm={async () => {
          haptic('warn')
          await deleteSession(session.id)
          pushToast({ kind: 'success', title: 'Workout gelöscht' })
          navigate('/history', { replace: true })
        }}
      />
    </div>
  )
}
