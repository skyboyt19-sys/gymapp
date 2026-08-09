import { useMemo, useState } from 'react'
import { calcPlates, displayToKg, kgToDisplay, trimNum } from '../lib/calc'
import { useApp } from '../state/AppState'
import { NumberField } from './ui'

const PLATE_COLORS: Record<number, string> = {
  25: '#ef4444',
  20: '#3b82f6',
  15: '#eab308',
  10: '#22c55e',
  5: '#f5f5f7',
  2.5: '#f97316',
  1.25: '#a1a1aa',
}

/** Zeigt, welche Scheiben pro Seite auf die Stange müssen. */
export function PlateCalculator({ initialKg = 0 }: { initialKg?: number }) {
  const { settings } = useApp()
  const [targetDisplay, setTargetDisplay] = useState(
    Math.round(kgToDisplay(initialKg || settings.barWeight, settings.unit) * 100) / 100,
  )

  const targetKg = displayToKg(targetDisplay, settings.unit)
  const result = useMemo(
    () => calcPlates(targetKg, settings.barWeight, settings.plates),
    [targetKg, settings.barWeight, settings.plates],
  )

  const counts = useMemo(() => {
    const map = new Map<number, number>()
    for (const p of result.plates) map.set(p, (map.get(p) ?? 0) + 1)
    return [...map.entries()].sort((a, b) => b[0] - a[0])
  }, [result.plates])

  return (
    <div>
      <label className="label mb-1.5 block">Zielgewicht ({settings.unit})</label>
      <NumberField
        className="field mb-4 text-center text-2xl font-bold tnum"
        value={targetDisplay}
        onCommit={setTargetDisplay}
        placeholder="Gewicht"
      />

      <div className="card p-4">
        <div className="text-sm text-mute">
          Stange {trimNum(kgToDisplay(settings.barWeight, settings.unit))} {settings.unit} · pro Seite:
        </div>

        {counts.length === 0 ? (
          <p className="mt-3 text-mute">Nur die Stange — keine Scheiben nötig.</p>
        ) : (
          <div className="mt-3 flex flex-wrap gap-2">
            {counts.map(([plate, count]) => (
              <div
                key={plate}
                className="flex items-center gap-2 rounded-xl border border-ink-600 bg-ink-800 px-3 py-2"
              >
                <span
                  className="h-6 w-2.5 rounded-sm"
                  style={{ background: PLATE_COLORS[plate] ?? '#71717a' }}
                />
                <span className="font-semibold tnum">
                  {count}× {trimNum(kgToDisplay(plate, settings.unit))}
                </span>
              </div>
            ))}
          </div>
        )}

        <div className="mt-4 flex items-baseline justify-between border-t border-ink-700 pt-3">
          <span className="text-sm text-mute">Ergibt</span>
          <span className="text-lg font-bold tnum">
            {trimNum(kgToDisplay(result.achievable, settings.unit))} {settings.unit}
          </span>
        </div>
        {result.rest > 0.01 && (
          <p className="mt-1 text-xs text-amber-400">
            {trimNum(kgToDisplay(result.rest, settings.unit))} {settings.unit} lassen sich mit deinen Scheiben nicht
            genau darstellen.
          </p>
        )}
      </div>

      <p className="mt-3 text-xs text-mute">
        Stangengewicht und verfügbare Scheiben kannst du in den Einstellungen anpassen.
      </p>
    </div>
  )
}
