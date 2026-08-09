import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useLiveQuery } from 'dexie-react-hooks'
import { db, uid } from '../db/db'
import type { Category, Program, Routine } from '../db/types'
import { CATEGORIES } from '../db/types'
import { ConfirmDialog, EmptyState, NavHeader, Sheet, Stepper } from '../components/ui'
import { useApp } from '../state/AppState'
import { generateProgram } from '../lib/generator'
import type { Goal } from '../lib/generator'
import { haptic } from '../lib/feedback'

const GOALS: { key: Goal; title: string; hint: string }[] = [
  { key: 'Kraft', title: 'Kraft', hint: 'Schwer, wenige Wiederholungen (5×5), lange Pausen' },
  { key: 'Hypertrophie', title: 'Muskelaufbau', hint: 'Mittlere Lasten, 4×10, moderate Pausen' },
  { key: 'Ausdauer', title: 'Kraftausdauer', hint: 'Leichter, 3×16, kurze Pausen' },
]

export default function Programs() {
  const navigate = useNavigate()
  const { pushToast } = useApp()
  const [genOpen, setGenOpen] = useState(false)
  const [deleteId, setDeleteId] = useState<string | null>(null)

  const [goal, setGoal] = useState<Goal>('Hypertrophie')
  const [days, setDays] = useState(3)
  const [equipment, setEquipment] = useState<Category[]>([
    'Langhantel',
    'Kurzhantel',
    'Maschine',
    'Kabel',
    'Körpergewicht',
  ])
  const [busy, setBusy] = useState(false)

  const programs = useLiveQuery(async () => await db.programs.toArray(), [], [] as Program[])
  const routines = useLiveQuery(async () => await db.routines.toArray(), [], [] as Routine[])

  const generate = async () => {
    if (busy) return
    setBusy(true)
    try {
      const { program } = await generateProgram({ goal, daysPerWeek: days, equipment })
      haptic('success')
      pushToast({ kind: 'success', title: 'Programm erstellt', message: program.name })
      setGenOpen(false)
    } catch (err) {
      console.error(err)
      pushToast({ kind: 'error', title: 'Erstellung fehlgeschlagen' })
    } finally {
      setBusy(false)
    }
  }

  const createEmpty = async () => {
    const now = Date.now()
    await db.programs.add({
      id: uid('prog'),
      name: 'Neues Programm',
      createdAt: now,
      updatedAt: now,
    })
  }

  return (
    <div className="animate-page min-h-full">
      <NavHeader
        title="Programme"
        backLabel="Start"
        onBack={() => navigate('/')}
        right={
          <button className="text-brand font-medium" onClick={() => setGenOpen(true)}>
            Generator
          </button>
        }
      />

      <div className="px-4 pb-tab">
        {programs.length === 0 ? (
          <div className="mt-6">
            <EmptyState
              icon="🗂️"
              title="Noch kein Programm"
              message="Ein Programm bündelt mehrere Routinen — z. B. Push/Pull/Legs. Der Generator baut dir in Sekunden einen passenden Split."
              action={
                <button className="btn-primary" onClick={() => setGenOpen(true)}>
                  Programm generieren
                </button>
              }
            />
          </div>
        ) : (
          programs.map((p) => {
            const list = routines
              .filter((r) => r.programId === p.id)
              .sort((a, b) => a.order - b.order)
            return (
              <section key={p.id} className="mt-5">
                <div className="mb-2 flex items-center justify-between gap-3 px-1">
                  <div className="min-w-0">
                    <h2 className="truncate font-semibold">{p.name}</h2>
                    <p className="text-xs text-mute">
                      {p.goal ? `${p.goal} · ` : ''}
                      {p.daysPerWeek ? `${p.daysPerWeek}× pro Woche · ` : ''}
                      {list.length} Routinen
                    </p>
                  </div>
                  <button className="shrink-0 text-sm text-red-400" onClick={() => setDeleteId(p.id)}>
                    Löschen
                  </button>
                </div>
                <div className="card divide-y divide-ink-700 overflow-hidden">
                  {list.length === 0 && <p className="px-4 py-4 text-sm text-mute">Keine Routinen in diesem Programm.</p>}
                  {list.map((r) => (
                    <button
                      key={r.id}
                      className="flex w-full items-center gap-3 px-4 py-3.5 text-left active:bg-ink-800"
                      onClick={() => navigate(`/routines/${r.id}`)}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="truncate font-medium">{r.name}</div>
                        <div className="text-xs text-mute">
                          {r.exercises.length} Übungen{r.notes ? ` · ${r.notes}` : ''}
                        </div>
                      </div>
                      <span className="text-mute">›</span>
                    </button>
                  ))}
                </div>
              </section>
            )
          })
        )}

        <div className="mt-6 space-y-2.5">
          <button className="btn-secondary w-full" onClick={() => setGenOpen(true)}>
            Programm generieren
          </button>
          <button className="btn-ghost w-full" onClick={createEmpty}>
            Leeres Programm anlegen
          </button>
        </div>
      </div>

      <Sheet
        open={genOpen}
        onClose={() => setGenOpen(false)}
        title="Programm-Generator"
        full
        footer={
          <button className="btn-primary w-full" disabled={busy} onClick={generate}>
            {busy ? 'Erstelle…' : 'Programm erstellen'}
          </button>
        }
      >
        <label className="label mb-2 block">Ziel</label>
        <div className="mb-5 space-y-2">
          {GOALS.map((g) => (
            <button
              key={g.key}
              className={`w-full rounded-xl px-4 py-3 text-left transition ${
                goal === g.key ? 'bg-white text-black' : 'bg-ink-800'
              }`}
              onClick={() => {
                haptic()
                setGoal(g.key)
              }}
            >
              <div className="font-semibold">{g.title}</div>
              <div className={`text-xs ${goal === g.key ? 'text-black/60' : 'text-mute'}`}>{g.hint}</div>
            </button>
          ))}
        </div>

        <div className="card mb-5 p-4">
          <Stepper label="Trainingstage pro Woche" value={days} min={1} max={7} onChange={setDays} />
        </div>

        <label className="label mb-2 block">Verfügbares Equipment</label>
        <div className="flex flex-wrap gap-2">
          {CATEGORIES.filter((c) => c !== 'Cardio').map((c) => (
            <button
              key={c}
              className={`chip ${equipment.includes(c) ? 'chip-active' : ''}`}
              onClick={() =>
                setEquipment((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]))
              }
            >
              {c}
            </button>
          ))}
        </div>
        <p className="mt-4 text-xs text-mute">
          Der Generator wählt passende Übungen aus deiner Bibliothek — Grundübungen zuerst. Danach kannst du jede
          Routine frei anpassen.
        </p>
      </Sheet>

      <ConfirmDialog
        open={!!deleteId}
        title="Programm löschen?"
        message="Die zugehörigen Routinen werden ebenfalls gelöscht. Absolvierte Workouts bleiben erhalten."
        onCancel={() => setDeleteId(null)}
        onConfirm={async () => {
          const pid = deleteId!
          setDeleteId(null)
          await db.routines.where('programId').equals(pid).delete()
          await db.programs.delete(pid)
          pushToast({ kind: 'success', title: 'Programm gelöscht' })
        }}
      />
    </div>
  )
}
