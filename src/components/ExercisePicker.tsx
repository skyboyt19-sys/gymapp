import { useMemo, useState } from 'react'
import { useLiveQuery } from 'dexie-react-hooks'
import { db } from '../db/db'
import type { Exercise, MuscleGroup } from '../db/types'
import { MUSCLE_GROUPS } from '../db/types'
import { Sheet } from './ui'
import { haptic } from '../lib/feedback'

export function matchesQuery(ex: Exercise, q: string): boolean {
  if (!q) return true
  const needle = q.toLowerCase().trim()
  return (
    ex.name.toLowerCase().includes(needle) ||
    ex.primary.toLowerCase().includes(needle) ||
    ex.secondary.some((m) => m.toLowerCase().includes(needle)) ||
    ex.category.toLowerCase().includes(needle)
  )
}

/**
 * Auswahl-Sheet für Übungen. Mehrfachauswahl, Suche nach Name/Muskel,
 * Filter nach Muskelgruppe. Bereits enthaltene Übungen werden markiert.
 */
export function ExercisePicker({
  open,
  onClose,
  onPick,
  excludeIds = [],
  title = 'Übungen hinzufügen',
}: {
  open: boolean
  onClose: () => void
  onPick: (ids: string[]) => void
  excludeIds?: string[]
  title?: string
}) {
  const [query, setQuery] = useState('')
  const [muscle, setMuscle] = useState<MuscleGroup | 'Alle'>('Alle')
  const [selected, setSelected] = useState<string[]>([])

  const exercises = useLiveQuery(async () => {
    const all = await db.exercises.toArray()
    return all.filter((e) => !e.archived).sort((a, b) => a.name.localeCompare(b.name, 'de'))
  }, [])

  const excluded = useMemo(() => new Set(excludeIds), [excludeIds])

  const filtered = useMemo(() => {
    const list = (exercises ?? []).filter(
      (e) => matchesQuery(e, query) && (muscle === 'Alle' || e.primary === muscle || e.secondary.includes(muscle)),
    )
    return list
  }, [exercises, query, muscle])

  const grouped = useMemo(() => {
    const map = new Map<MuscleGroup, Exercise[]>()
    for (const ex of filtered) {
      const arr = map.get(ex.primary) ?? []
      arr.push(ex)
      map.set(ex.primary, arr)
    }
    return MUSCLE_GROUPS.filter((m) => map.has(m)).map((m) => [m, map.get(m)!] as const)
  }, [filtered])

  const close = () => {
    setSelected([])
    setQuery('')
    setMuscle('Alle')
    onClose()
  }

  const confirm = () => {
    if (selected.length) onPick(selected)
    close()
  }

  return (
    <Sheet open={open} onClose={close} title={title} full
      footer={
        <button className="btn-primary w-full" disabled={selected.length === 0} onClick={confirm}>
          {selected.length === 0
            ? 'Übungen auswählen'
            : `${selected.length} ${selected.length === 1 ? 'Übung' : 'Übungen'} hinzufügen`}
        </button>
      }
    >
      <input
        className="field mb-3"
        placeholder="Suchen (Name oder Muskel)…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        autoCorrect="off"
        autoCapitalize="none"
      />

      <div className="-mx-4 mb-4 flex gap-2 overflow-x-auto px-4 no-scrollbar">
        {(['Alle', ...MUSCLE_GROUPS] as const).map((m) => (
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

      {grouped.length === 0 && <p className="py-8 text-center text-mute">Keine Übung gefunden.</p>}

      {grouped.map(([group, list]) => (
        <div key={group} className="mb-5">
          <h4 className="label mb-2">{group}</h4>
          <div className="card overflow-hidden">
            {list.map((ex, i) => {
              const isSelected = selected.includes(ex.id)
              const already = excluded.has(ex.id)
              return (
                <button
                  key={ex.id}
                  disabled={already}
                  onClick={() => {
                    haptic()
                    setSelected((prev) =>
                      prev.includes(ex.id) ? prev.filter((id) => id !== ex.id) : [...prev, ex.id],
                    )
                  }}
                  className={`flex w-full items-center gap-3 px-4 py-3 text-left transition-colors ${
                    i > 0 ? 'border-t border-ink-700' : ''
                  } ${already ? 'opacity-40' : 'active:bg-ink-800'}`}
                >
                  <span
                    className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[13px] ${
                      isSelected ? 'border-white bg-white text-black' : 'border-ink-500 text-transparent'
                    }`}
                  >
                    ✓
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate">{ex.name}</span>
                    <span className="block text-xs text-mute truncate">
                      {ex.category}
                      {ex.secondary.length > 0 && ` · ${ex.secondary.join(', ')}`}
                    </span>
                  </span>
                  {already && <span className="text-xs text-mute shrink-0">dabei</span>}
                </button>
              )
            })}
          </div>
        </div>
      ))}
    </Sheet>
  )
}
