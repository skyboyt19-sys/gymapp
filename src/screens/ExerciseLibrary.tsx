import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useLiveQuery } from 'dexie-react-hooks'
import { db, uid } from '../db/db'
import type { Category, Exercise, MuscleGroup } from '../db/types'
import { CATEGORIES, MUSCLE_GROUPS } from '../db/types'
import { EmptyState, Screen, Sheet, Stepper, Toggle } from '../components/ui'
import { matchesQuery } from '../components/ExercisePicker'
import { useApp } from '../state/AppState'
import { haptic } from '../lib/feedback'

export default function ExerciseLibrary() {
  const navigate = useNavigate()
  const { pushToast } = useApp()
  const [query, setQuery] = useState('')
  const [muscle, setMuscle] = useState<MuscleGroup | 'Alle' | 'Eigene'>('Alle')
  const [newOpen, setNewOpen] = useState(false)

  const exercises = useLiveQuery(
    async () => (await db.exercises.toArray()).filter((e) => !e.archived).sort((a, b) => a.name.localeCompare(b.name, 'de')),
    [],
    [] as Exercise[],
  )

  const filtered = useMemo(
    () =>
      exercises.filter(
        (e) =>
          matchesQuery(e, query) &&
          (muscle === 'Alle' ||
            (muscle === 'Eigene' ? e.custom : e.primary === muscle || e.secondary.includes(muscle))),
      ),
    [exercises, query, muscle],
  )

  const grouped = useMemo(() => {
    const map = new Map<MuscleGroup, Exercise[]>()
    for (const ex of filtered) {
      const arr = map.get(ex.primary) ?? []
      arr.push(ex)
      map.set(ex.primary, arr)
    }
    return MUSCLE_GROUPS.filter((m) => map.has(m)).map((m) => [m, map.get(m)!] as const)
  }, [filtered])

  return (
    <Screen
      title="Übungen"
      subtitle={`${exercises.length} Übungen · ${exercises.filter((e) => e.custom).length} eigene`}
      right={
        <button className="btn-primary px-3 text-sm" onClick={() => setNewOpen(true)}>
          Neu
        </button>
      }
    >
      <input
        className="field mt-1"
        placeholder="Suchen (Name oder Muskel)…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        autoCorrect="off"
        autoCapitalize="none"
      />

      <div className="-mx-4 mt-3 flex gap-2 overflow-x-auto px-4 no-scrollbar">
        {(['Alle', 'Eigene', ...MUSCLE_GROUPS] as const).map((m) => (
          <button
            key={m}
            className={`chip ${muscle === m ? 'chip-active' : ''}`}
            onClick={() => {
              haptic()
              setMuscle(m)
            }}
          >
            {m}
          </button>
        ))}
      </div>

      {grouped.length === 0 ? (
        <div className="mt-6">
          <EmptyState
            icon="🔍"
            title="Nichts gefunden"
            message="Passe die Suche an oder lege eine eigene Übung an."
            action={
              <button className="btn-secondary" onClick={() => setNewOpen(true)}>
                Eigene Übung
              </button>
            }
          />
        </div>
      ) : (
        grouped.map(([group, list]) => (
          <div key={group} className="mt-6">
            <h2 className="label mb-2 px-1">
              {group} <span className="text-mute/60">({list.length})</span>
            </h2>
            <div className="card divide-y divide-ink-700 overflow-hidden">
              {list.map((ex) => (
                <button
                  key={ex.id}
                  className="flex w-full items-center gap-3 px-4 py-3 text-left active:bg-ink-800"
                  onClick={() => navigate(`/exercises/${ex.id}`)}
                >
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">
                      {ex.name}
                      {ex.custom && <span className="ml-2 text-[10px] text-brand">EIGEN</span>}
                    </div>
                    <div className="truncate text-xs text-mute">
                      {ex.category}
                      {ex.secondary.length > 0 && ` · ${ex.secondary.join(', ')}`}
                    </div>
                  </div>
                  <span className="text-mute">›</span>
                </button>
              ))}
            </div>
          </div>
        ))
      )}

      <ExerciseEditor
        open={newOpen}
        onClose={() => setNewOpen(false)}
        onSaved={(id) => {
          pushToast({ kind: 'success', title: 'Übung angelegt' })
          navigate(`/exercises/${id}`)
        }}
      />
    </Screen>
  )
}

/** Sheet zum Anlegen oder Bearbeiten einer Übung. */
export function ExerciseEditor({
  open,
  onClose,
  existing,
  onSaved,
}: {
  open: boolean
  onClose: () => void
  existing?: Exercise
  onSaved?: (id: string) => void
}) {
  const [name, setName] = useState(existing?.name ?? '')
  const [primary, setPrimary] = useState<MuscleGroup>(existing?.primary ?? 'Brust')
  const [secondary, setSecondary] = useState<MuscleGroup[]>(existing?.secondary ?? [])
  const [category, setCategory] = useState<Category>(existing?.category ?? 'Langhantel')
  const [instructions, setInstructions] = useState(existing?.instructions ?? '')
  const [restSec, setRestSec] = useState(existing?.restSec ?? 90)
  const [timeBased, setTimeBased] = useState(existing?.timeBased ?? false)
  const [error, setError] = useState('')

  const save = async () => {
    const trimmed = name.trim()
    if (!trimmed) {
      setError('Bitte gib einen Namen ein.')
      return
    }
    const now = Date.now()
    if (existing) {
      await db.exercises.update(existing.id, {
        name: trimmed,
        primary,
        secondary,
        category,
        instructions,
        restSec,
        timeBased,
        updatedAt: now,
      })
      onSaved?.(existing.id)
    } else {
      const id = uid('ex')
      await db.exercises.add({
        id,
        name: trimmed,
        primary,
        secondary,
        category,
        instructions,
        restSec,
        timeBased,
        custom: true,
        createdAt: now,
        updatedAt: now,
      })
      setName('')
      setInstructions('')
      setSecondary([])
      onSaved?.(id)
    }
    onClose()
  }

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={existing ? 'Übung bearbeiten' : 'Eigene Übung'}
      full
      footer={
        <button className="btn-primary w-full" onClick={save}>
          Speichern
        </button>
      }
    >
      {error && <p className="mb-3 text-sm text-red-400">{error}</p>}

      <label className="label mb-1.5 block">Name</label>
      <input
        className="field mb-4"
        value={name}
        onChange={(e) => {
          setName(e.target.value)
          setError('')
        }}
        placeholder="z. B. Bankdrücken eng"
      />

      <label className="label mb-1.5 block">Primäre Muskelgruppe</label>
      <div className="mb-4 flex flex-wrap gap-2">
        {MUSCLE_GROUPS.map((m) => (
          <button
            key={m}
            className={`chip ${primary === m ? 'chip-active' : ''}`}
            onClick={() => setPrimary(m)}
          >
            {m}
          </button>
        ))}
      </div>

      <label className="label mb-1.5 block">Zusätzliche Muskelgruppen</label>
      <div className="mb-4 flex flex-wrap gap-2">
        {MUSCLE_GROUPS.filter((m) => m !== primary).map((m) => (
          <button
            key={m}
            className={`chip ${secondary.includes(m) ? 'chip-active' : ''}`}
            onClick={() =>
              setSecondary((prev) => (prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m]))
            }
          >
            {m}
          </button>
        ))}
      </div>

      <label className="label mb-1.5 block">Kategorie</label>
      <div className="mb-4 flex flex-wrap gap-2">
        {CATEGORIES.map((c) => (
          <button key={c} className={`chip ${category === c ? 'chip-active' : ''}`} onClick={() => setCategory(c)}>
            {c}
          </button>
        ))}
      </div>

      <label className="label mb-1.5 block">Kurzanleitung / Tipps</label>
      <textarea
        className="field mb-4 min-h-24"
        value={instructions}
        onChange={(e) => setInstructions(e.target.value)}
        placeholder="Worauf achtest du bei der Ausführung?"
      />

      <div className="card mb-4 px-4">
        <Toggle
          checked={timeBased}
          onChange={setTimeBased}
          label="Zeitbasierte Übung"
          hint="Dauer statt Wiederholungen erfassen (z. B. Plank, Cardio)."
        />
      </div>

      <div className="card mb-2 p-4">
        <Stepper
          label="Standard-Pausenzeit"
          value={restSec}
          step={15}
          min={0}
          max={600}
          suffix="Sek"
          onChange={setRestSec}
        />
      </div>
    </Sheet>
  )
}
