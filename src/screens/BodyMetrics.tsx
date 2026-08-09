import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useLiveQuery } from 'dexie-react-hooks'
import { db, uid } from '../db/db'
import type { BodyMetric } from '../db/types'
import { ConfirmDialog, EmptyState, NavHeader, Sheet } from '../components/ui'
import { SimpleLineChart } from '../components/Charts'
import { useApp } from '../state/AppState'
import { kgToDisplay, displayToKg, trimNum } from '../lib/calc'
import { formatDate, formatDateShort, todayISO } from '../lib/format'

type Field = keyof Pick<
  BodyMetric,
  'weight' | 'bodyFat' | 'chest' | 'waist' | 'hips' | 'armLeft' | 'armRight' | 'thighLeft' | 'thighRight'
>

const FIELDS: { key: Field; label: string; unit: 'weight' | '%' | 'cm' }[] = [
  { key: 'weight', label: 'Körpergewicht', unit: 'weight' },
  { key: 'bodyFat', label: 'Körperfett', unit: '%' },
  { key: 'chest', label: 'Brust', unit: 'cm' },
  { key: 'waist', label: 'Taille', unit: 'cm' },
  { key: 'hips', label: 'Hüfte', unit: 'cm' },
  { key: 'armLeft', label: 'Arm links', unit: 'cm' },
  { key: 'armRight', label: 'Arm rechts', unit: 'cm' },
  { key: 'thighLeft', label: 'Oberschenkel links', unit: 'cm' },
  { key: 'thighRight', label: 'Oberschenkel rechts', unit: 'cm' },
]

export default function BodyMetrics() {
  const navigate = useNavigate()
  const { settings, pushToast } = useApp()
  const [open, setOpen] = useState(false)
  const [chartField, setChartField] = useState<Field>('weight')
  const [deleteId, setDeleteId] = useState<string | null>(null)
  const [draft, setDraft] = useState<Partial<BodyMetric>>({ date: todayISO() })

  const entries = useLiveQuery(
    async () => (await db.bodyMetrics.toArray()).sort((a, b) => b.date.localeCompare(a.date)),
    [],
    [] as BodyMetric[],
  )

  const chartData = useMemo(() => {
    const list = entries
      .filter((e) => typeof e[chartField] === 'number')
      .sort((a, b) => a.date.localeCompare(b.date))
      .slice(-60)
    return list.map((e) => ({
      label: formatDateShort(e.date),
      value:
        chartField === 'weight' ? kgToDisplay(e.weight ?? 0, settings.unit) : (e[chartField] as number),
    }))
  }, [entries, chartField, settings.unit])

  const unitFor = (f: Field) => {
    const def = FIELDS.find((x) => x.key === f)!
    return def.unit === 'weight' ? settings.unit : def.unit
  }

  const save = async () => {
    const hasValue = FIELDS.some((f) => typeof draft[f.key] === 'number' && !Number.isNaN(draft[f.key]))
    if (!hasValue) {
      pushToast({ kind: 'error', title: 'Kein Wert eingetragen' })
      return
    }
    const date = draft.date || todayISO()
    const existing = entries.find((e) => e.date === date)
    if (existing) {
      await db.bodyMetrics.update(existing.id, { ...draft, date })
    } else {
      await db.bodyMetrics.add({
        id: uid('bm'),
        date,
        createdAt: Date.now(),
        ...draft,
      } as BodyMetric)
    }
    setDraft({ date: todayISO() })
    setOpen(false)
    pushToast({ kind: 'success', title: 'Gespeichert' })
  }

  const latest = entries[0]

  return (
    <div className="animate-page min-h-full">
      <NavHeader
        title="Körperdaten"
        backLabel="Start"
        onBack={() => navigate('/')}
        right={
          <button
            className="text-brand font-medium"
            onClick={() => {
              setDraft({ date: todayISO() })
              setOpen(true)
            }}
          >
            Neu
          </button>
        }
      />

      <div className="px-4 pb-tab">
        {entries.length === 0 ? (
          <div className="mt-6">
            <EmptyState
              icon="⚖️"
              title="Noch keine Einträge"
              message="Trage Körpergewicht und Maße ein, um deine Entwicklung als Graph zu sehen."
              action={
                <button className="btn-primary" onClick={() => setOpen(true)}>
                  Ersten Eintrag anlegen
                </button>
              }
            />
          </div>
        ) : (
          <>
            {latest && (
              <div className="card mt-3 p-4">
                <div className="label">Aktuell ({formatDate(latest.date)})</div>
                <div className="mt-2 flex flex-wrap gap-x-6 gap-y-2">
                  {FIELDS.filter((f) => typeof latest[f.key] === 'number').map((f) => (
                    <div key={f.key}>
                      <div className="text-xs text-mute">{f.label}</div>
                      <div className="text-lg font-semibold tnum">
                        {f.key === 'weight'
                          ? trimNum(kgToDisplay(latest.weight ?? 0, settings.unit), 1)
                          : trimNum(latest[f.key] as number, 1)}{' '}
                        <span className="text-xs text-mute">{unitFor(f.key)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="-mx-4 mt-4 flex gap-2 overflow-x-auto px-4 no-scrollbar">
              {FIELDS.map((f) => (
                <button
                  key={f.key}
                  className={`chip ${chartField === f.key ? 'chip-active' : ''}`}
                  onClick={() => setChartField(f.key)}
                >
                  {f.label}
                </button>
              ))}
            </div>

            <div className="card mt-3 p-3 pt-4">
              <SimpleLineChart
                data={chartData}
                unit={unitFor(chartField)}
                name={FIELDS.find((f) => f.key === chartField)!.label}
              />
            </div>

            <h2 className="label mb-2 mt-6 px-1">Alle Einträge</h2>
            <div className="card divide-y divide-ink-700 overflow-hidden">
              {entries.map((e) => (
                <div key={e.id} className="flex items-center gap-3 px-4 py-3">
                  <button
                    className="min-w-0 flex-1 text-left"
                    onClick={() => {
                      setDraft(e)
                      setOpen(true)
                    }}
                  >
                    <div className="text-sm font-medium">{formatDate(e.date)}</div>
                    <div className="mt-0.5 text-xs text-mute">
                      {FIELDS.filter((f) => typeof e[f.key] === 'number')
                        .map(
                          (f) =>
                            `${f.label}: ${
                              f.key === 'weight'
                                ? trimNum(kgToDisplay(e.weight ?? 0, settings.unit), 1)
                                : trimNum(e[f.key] as number, 1)
                            } ${unitFor(f.key)}`,
                        )
                        .join(' · ')}
                    </div>
                  </button>
                  <button className="shrink-0 text-sm text-red-400" onClick={() => setDeleteId(e.id)}>
                    Löschen
                  </button>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      <Sheet
        open={open}
        onClose={() => setOpen(false)}
        title="Eintrag"
        full
        footer={
          <button className="btn-primary w-full" onClick={save}>
            Speichern
          </button>
        }
      >
        <label className="label mb-1.5 block">Datum</label>
        <input
          type="date"
          className="field mb-4"
          value={draft.date ?? todayISO()}
          onChange={(e) => setDraft((d) => ({ ...d, date: e.target.value }))}
        />

        {FIELDS.map((f) => (
          <div key={f.key} className="mb-3">
            <label className="label mb-1.5 block">
              {f.label} ({unitFor(f.key)})
            </label>
            <input
              className="field"
              inputMode="decimal"
              value={
                typeof draft[f.key] === 'number'
                  ? f.key === 'weight'
                    ? String(Math.round(kgToDisplay(draft.weight ?? 0, settings.unit) * 100) / 100)
                    : String(draft[f.key])
                  : ''
              }
              placeholder="—"
              onChange={(e) => {
                const raw = e.target.value.replace(',', '.')
                const n = parseFloat(raw)
                setDraft((d) => ({
                  ...d,
                  [f.key]: raw === '' || Number.isNaN(n)
                    ? undefined
                    : f.key === 'weight'
                      ? displayToKg(n, settings.unit)
                      : n,
                }))
              }}
            />
          </div>
        ))}

        <label className="label mb-1.5 block">Notiz</label>
        <textarea
          className="field min-h-20"
          value={draft.notes ?? ''}
          onChange={(e) => setDraft((d) => ({ ...d, notes: e.target.value }))}
        />
      </Sheet>

      <ConfirmDialog
        open={!!deleteId}
        title="Eintrag löschen?"
        onCancel={() => setDeleteId(null)}
        onConfirm={async () => {
          await db.bodyMetrics.delete(deleteId!)
          setDeleteId(null)
        }}
      />
    </div>
  )
}
