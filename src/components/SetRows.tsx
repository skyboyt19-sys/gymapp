import { useState } from 'react'
import type { Exercise, SetLog, SetType, Unit } from '../db/types'
import { NumberField, Sheet } from './ui'
import { displayToKg, kgToDisplay } from '../lib/calc'
import { formatDuration } from '../lib/format'
import { haptic } from '../lib/feedback'

const TYPE_BADGE: Record<SetType, { label: string; cls: string }> = {
  normal: { label: '', cls: 'bg-ink-700 text-white' },
  warmup: { label: 'W', cls: 'bg-amber-500/25 text-amber-300' },
  dropset: { label: 'D', cls: 'bg-purple-500/25 text-purple-300' },
}

export interface SetRowProps {
  set: SetLog
  exercise: Exercise
  unit: Unit
  /** Vorschlag aus dem letzten Workout */
  previous?: SetLog
  showRpe: boolean
  onUpdate: (patch: Partial<SetLog>) => void
  onToggleDone: () => void
  onDelete: () => void
  readOnly?: boolean
}

export function SetRow({
  set,
  exercise,
  unit,
  previous,
  showRpe,
  onUpdate,
  onToggleDone,
  onDelete,
  readOnly,
}: SetRowProps) {
  const [menuOpen, setMenuOpen] = useState(false)
  const badge = TYPE_BADGE[set.type]

  const prevText = previous
    ? exercise.timeBased
      ? formatDuration(previous.seconds ?? 0)
      : `${Math.round(kgToDisplay(previous.weight, unit) * 10) / 10}×${previous.reps}`
    : '—'

  return (
    <>
      <div
        className={`flex items-center gap-2 px-2 py-1.5 ${set.done ? 'bg-green-600/10' : ''} transition-colors`}
      >
        <button
          className={`h-8 w-8 shrink-0 rounded-lg text-[13px] font-semibold tnum ${badge.cls}`}
          onClick={() => {
            haptic()
            setMenuOpen(true)
          }}
          aria-label={`Satz ${set.setNumber} Optionen`}
        >
          {badge.label || set.setNumber}
        </button>

        <div className="w-14 shrink-0 truncate text-center text-[11px] text-mute tnum">{prevText}</div>

        {exercise.timeBased ? (
          <div className="flex flex-1 items-center gap-1.5">
            <NumberField
              ariaLabel="Dauer in Sekunden"
              className="field min-w-0 flex-1 px-2 py-2 text-center tnum"
              value={set.seconds ?? 0}
              decimals={0}
              placeholder="Sek"
              onCommit={(v) => onUpdate({ seconds: Math.round(v) })}
            />
            <span className="text-xs text-mute">Sek</span>
          </div>
        ) : (
          <>
            <NumberField
              ariaLabel="Gewicht"
              className="field min-w-0 flex-1 px-2 py-2 text-center tnum"
              value={Math.round(kgToDisplay(set.weight, unit) * 100) / 100}
              placeholder={unit}
              onCommit={(v) => onUpdate({ weight: displayToKg(v, unit) })}
            />
            <NumberField
              ariaLabel="Wiederholungen"
              className="field min-w-0 flex-1 px-2 py-2 text-center tnum"
              value={set.reps}
              decimals={0}
              placeholder="Wdh"
              onCommit={(v) => onUpdate({ reps: Math.round(v) })}
            />
          </>
        )}

        {showRpe && (
          <NumberField
            ariaLabel="RPE"
            className="field w-14 shrink-0 px-1 py-2 text-center tnum"
            value={set.rpe ?? 0}
            decimals={1}
            placeholder="RPE"
            onCommit={(v) => onUpdate({ rpe: v > 0 ? Math.min(10, v) : undefined })}
          />
        )}

        <button
          onClick={onToggleDone}
          aria-label={set.done ? 'Satz zurücksetzen' : 'Satz erledigt'}
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border text-base transition ${
            set.done
              ? 'border-green-500 bg-green-500 text-black'
              : 'border-ink-500 bg-ink-800 text-transparent active:bg-ink-700'
          }`}
        >
          ✓
        </button>
      </div>

      <Sheet open={menuOpen} onClose={() => setMenuOpen(false)} title={`Satz ${set.setNumber}`}>
        <div className="space-y-2">
          <p className="label mb-1">Satz-Typ</p>
          {(['normal', 'warmup', 'dropset'] as SetType[]).map((t) => (
            <button
              key={t}
              className={`w-full rounded-xl px-4 py-3 text-left ${
                set.type === t ? 'bg-white text-black' : 'bg-ink-800'
              }`}
              onClick={() => {
                haptic()
                onUpdate({ type: t })
                setMenuOpen(false)
              }}
            >
              {t === 'normal' ? 'Normaler Satz' : t === 'warmup' ? 'Aufwärmsatz (zählt nicht für Rekorde)' : 'Dropset'}
            </button>
          ))}
          {!readOnly && (
            <button
              className="btn-danger mt-4 w-full"
              onClick={() => {
                onDelete()
                setMenuOpen(false)
              }}
            >
              Satz löschen
            </button>
          )}
        </div>
      </Sheet>
    </>
  )
}

export function SetHeader({
  timeBased,
  unit,
  showRpe,
}: {
  timeBased: boolean
  unit: Unit
  showRpe: boolean
}) {
  return (
    <div className="flex items-center gap-2 px-2 pb-1 pt-1 text-[10px] font-medium uppercase tracking-wider text-mute">
      <div className="w-8 shrink-0 text-center">Satz</div>
      <div className="w-14 shrink-0 text-center">Vorher</div>
      {timeBased ? (
        <div className="flex-1 text-center">Dauer</div>
      ) : (
        <>
          <div className="flex-1 text-center">{unit}</div>
          <div className="flex-1 text-center">Wdh.</div>
        </>
      )}
      {showRpe && <div className="w-14 shrink-0 text-center">RPE</div>}
      <div className="w-9 shrink-0" />
    </div>
  )
}
