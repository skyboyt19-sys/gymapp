import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useLiveQuery } from 'dexie-react-hooks'
import { db, uid } from '../db/db'
import type { Program, Routine } from '../db/types'
import { EmptyState, NavHeader, Sheet } from '../components/ui'
import { useWorkout } from '../state/WorkoutState'
import { relativeDays, todayISO } from '../lib/format'
import { haptic } from '../lib/feedback'

export default function Routines() {
  const navigate = useNavigate()
  const { session, startWorkout } = useWorkout()
  const [newOpen, setNewOpen] = useState(false)
  const [name, setName] = useState('')

  const routines = useLiveQuery(
    async () => (await db.routines.toArray()).sort((a, b) => a.order - b.order || a.name.localeCompare(b.name, 'de')),
    [],
    [] as Routine[],
  )
  const programs = useLiveQuery(async () => await db.programs.toArray(), [], [] as Program[])

  const create = async () => {
    const trimmed = name.trim() || 'Neue Routine'
    const now = Date.now()
    const id = uid('rt')
    await db.routines.add({
      id,
      name: trimmed,
      exercises: [],
      order: routines.length,
      createdAt: now,
      updatedAt: now,
    })
    setName('')
    setNewOpen(false)
    navigate(`/routines/${id}`)
  }

  const start = async (routineId: string) => {
    haptic('success')
    await startWorkout({ routineId })
    navigate('/workout')
  }

  const standalone = routines.filter((r) => !r.programId)
  const byProgram = programs
    .map((p) => ({ program: p, list: routines.filter((r) => r.programId === p.id) }))
    .filter((g) => g.list.length > 0)

  return (
    <div className="animate-page min-h-full">
      <NavHeader
        title="Routinen"
        backLabel="Start"
        onBack={() => navigate('/')}
        right={
          <button className="text-brand font-medium" onClick={() => setNewOpen(true)}>
            Neu
          </button>
        }
      />

      <div className="px-4 pb-tab">
        {routines.length === 0 ? (
          <div className="mt-6">
            <EmptyState
              icon="📋"
              title="Noch keine Routine"
              message="Eine Routine ist eine Vorlage: Übungen mit Ziel-Sätzen und -Wiederholungen. Beim Start ist alles schon vorbereitet."
              action={
                <button className="btn-primary" onClick={() => setNewOpen(true)}>
                  Routine erstellen
                </button>
              }
            />
          </div>
        ) : (
          <>
            {standalone.length > 0 && (
              <RoutineGroup title="Eigene Routinen" list={standalone} onOpen={(id) => navigate(`/routines/${id}`)} onStart={start} disabled={!!session} />
            )}
            {byProgram.map(({ program, list }) => (
              <RoutineGroup
                key={program.id}
                title={program.name}
                list={list}
                onOpen={(id) => navigate(`/routines/${id}`)}
                onStart={start}
                disabled={!!session}
              />
            ))}
          </>
        )}

        <button className="btn-secondary mt-6 w-full" onClick={() => navigate('/programs')}>
          Programme & Generator
        </button>
      </div>

      <Sheet
        open={newOpen}
        onClose={() => setNewOpen(false)}
        title="Neue Routine"
        footer={
          <button className="btn-primary w-full" onClick={create}>
            Erstellen
          </button>
        }
      >
        <label className="label mb-1.5 block">Name</label>
        <input
          className="field"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="z. B. Push A"
          autoFocus
        />
      </Sheet>
    </div>
  )
}

function RoutineGroup({
  title,
  list,
  onOpen,
  onStart,
  disabled,
}: {
  title: string
  list: Routine[]
  onOpen: (id: string) => void
  onStart: (id: string) => void
  disabled: boolean
}) {
  return (
    <section className="mt-5">
      <h2 className="label mb-2 px-1">{title}</h2>
      <div className="card divide-y divide-ink-700 overflow-hidden">
        {list.map((r) => (
          <div key={r.id} className="flex items-center">
            <button className="min-w-0 flex-1 px-4 py-3.5 text-left active:bg-ink-800" onClick={() => onOpen(r.id)}>
              <div className="truncate font-medium">{r.name}</div>
              <div className="mt-0.5 text-xs text-mute">
                {r.exercises.length} {r.exercises.length === 1 ? 'Übung' : 'Übungen'}
                {r.lastPerformedAt &&
                  ` · zuletzt ${relativeDays(todayISO(new Date(r.lastPerformedAt))).toLowerCase()}`}
              </div>
            </button>
            <button
              className="btn-secondary mr-3 px-3 text-sm"
              disabled={disabled || r.exercises.length === 0}
              onClick={() => onStart(r.id)}
            >
              Start
            </button>
          </div>
        ))}
      </div>
    </section>
  )
}
