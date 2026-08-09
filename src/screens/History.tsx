import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useLiveQuery } from 'dexie-react-hooks'
import { db } from '../db/db'
import type { WorkoutSession } from '../db/types'
import { EmptyState, Screen } from '../components/ui'
import { useApp } from '../state/AppState'
import { kgToDisplay, trimNum } from '../lib/calc'
import { addDays, formatDate, formatDurationLong, startOfWeek, todayISO } from '../lib/format'
import { haptic } from '../lib/feedback'

type View = 'list' | 'kalender'

export default function History() {
  const navigate = useNavigate()
  const { settings } = useApp()
  const [view, setView] = useState<View>('list')
  const [month, setMonth] = useState(() => {
    const d = new Date()
    return new Date(d.getFullYear(), d.getMonth(), 1)
  })

  const sessions = useLiveQuery(
    async () => (await db.sessions.toArray()).filter((s) => !s.active).sort((a, b) => b.startedAt - a.startedAt),
    [],
    [] as WorkoutSession[],
  )

  const byDate = useMemo(() => {
    const map = new Map<string, WorkoutSession[]>()
    for (const s of sessions) {
      const arr = map.get(s.date) ?? []
      arr.push(s)
      map.set(s.date, arr)
    }
    return map
  }, [sessions])

  const grouped = useMemo(() => {
    const map = new Map<string, WorkoutSession[]>()
    for (const s of sessions) {
      const d = new Date(s.startedAt)
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
      const arr = map.get(key) ?? []
      arr.push(s)
      map.set(key, arr)
    }
    return [...map.entries()]
  }, [sessions])

  const totals = useMemo(
    () => ({
      count: sessions.length,
      volume: sessions.reduce((a, s) => a + (s.totalVolume ?? 0), 0),
      time: sessions.reduce((a, s) => a + (s.durationSec ?? 0), 0),
    }),
    [sessions],
  )

  return (
    <Screen
      title="Verlauf"
      subtitle={`${totals.count} Workouts · ${formatDurationLong(totals.time)} · ${trimNum(
        Math.round(kgToDisplay(totals.volume, settings.unit)),
        0,
      )} ${settings.unit}`}
    >
      <div className="mt-1 flex gap-2">
        {(['list', 'kalender'] as View[]).map((v) => (
          <button
            key={v}
            className={`chip ${view === v ? 'chip-active' : ''}`}
            onClick={() => {
              haptic()
              setView(v)
            }}
          >
            {v === 'list' ? 'Liste' : 'Kalender'}
          </button>
        ))}
      </div>

      {sessions.length === 0 ? (
        <div className="mt-6">
          <EmptyState icon="📅" title="Noch keine Workouts" message="Sobald du ein Workout beendest, erscheint es hier." />
        </div>
      ) : view === 'kalender' ? (
        <CalendarView
          month={month}
          onMonthChange={setMonth}
          byDate={byDate}
          onPick={(id) => navigate(`/history/${id}`)}
        />
      ) : (
        <div className="mt-4 space-y-6">
          {grouped.map(([key, list]) => {
            const [y, m] = key.split('-').map(Number)
            const label = new Date(y, m - 1, 1).toLocaleDateString('de-DE', { month: 'long', year: 'numeric' })
            return (
              <div key={key}>
                <h2 className="label mb-2 px-1">{label}</h2>
                <div className="card divide-y divide-ink-700 overflow-hidden">
                  {list.map((s) => (
                    <button
                      key={s.id}
                      className="flex w-full items-center gap-3 px-4 py-3.5 text-left active:bg-ink-800"
                      onClick={() => navigate(`/history/${s.id}`)}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="truncate font-medium">{s.name}</div>
                        <div className="mt-0.5 text-xs text-mute">
                          {formatDate(s.date)} · {s.totalSets ?? 0} Sätze ·{' '}
                          {trimNum(Math.round(kgToDisplay(s.totalVolume ?? 0, settings.unit)), 0)} {settings.unit}
                        </div>
                      </div>
                      <div className="shrink-0 text-xs text-mute tnum">
                        {formatDurationLong(s.durationSec ?? 0)}
                      </div>
                      <span className="text-mute">›</span>
                    </button>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </Screen>
  )
}

function CalendarView({
  month,
  onMonthChange,
  byDate,
  onPick,
}: {
  month: Date
  onMonthChange: (d: Date) => void
  byDate: Map<string, WorkoutSession[]>
  onPick: (id: string) => void
}) {
  const [selected, setSelected] = useState<string | null>(null)

  const days = useMemo(() => {
    const first = new Date(month.getFullYear(), month.getMonth(), 1)
    const start = startOfWeek(first)
    return Array.from({ length: 42 }, (_, i) => addDays(start, i))
  }, [month])

  const today = todayISO()
  const selectedSessions = selected ? (byDate.get(selected) ?? []) : []

  return (
    <div className="mt-4">
      <div className="mb-3 flex items-center justify-between">
        <button
          className="btn-secondary px-3"
          onClick={() => onMonthChange(new Date(month.getFullYear(), month.getMonth() - 1, 1))}
        >
          ‹
        </button>
        <div className="font-semibold">
          {month.toLocaleDateString('de-DE', { month: 'long', year: 'numeric' })}
        </div>
        <button
          className="btn-secondary px-3"
          onClick={() => onMonthChange(new Date(month.getFullYear(), month.getMonth() + 1, 1))}
        >
          ›
        </button>
      </div>

      <div className="card p-3">
        <div className="mb-1 grid grid-cols-7 gap-1 text-center text-[10px] uppercase tracking-wider text-mute">
          {['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'].map((d) => (
            <div key={d}>{d}</div>
          ))}
        </div>
        <div className="grid grid-cols-7 gap-1">
          {days.map((d) => {
            const iso = todayISO(d)
            const has = byDate.has(iso)
            const inMonth = d.getMonth() === month.getMonth()
            return (
              <button
                key={iso}
                disabled={!has}
                onClick={() => {
                  haptic()
                  setSelected(iso === selected ? null : iso)
                }}
                className={`relative aspect-square rounded-lg text-sm tnum transition ${
                  has ? 'bg-green-600/25 font-semibold text-white' : inMonth ? 'text-white/70' : 'text-white/20'
                } ${selected === iso ? 'ring-2 ring-white' : ''} ${iso === today ? 'border border-brand' : ''}`}
              >
                {d.getDate()}
              </button>
            )
          })}
        </div>
      </div>

      {selected && (
        <div className="mt-4">
          <h3 className="label mb-2 px-1">{formatDate(selected)}</h3>
          {selectedSessions.length === 0 ? (
            <p className="px-1 text-sm text-mute">Kein Workout an diesem Tag.</p>
          ) : (
            <div className="card divide-y divide-ink-700 overflow-hidden">
              {selectedSessions.map((s) => (
                <button
                  key={s.id}
                  className="flex w-full items-center gap-3 px-4 py-3.5 text-left active:bg-ink-800"
                  onClick={() => onPick(s.id)}
                >
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">{s.name}</div>
                    <div className="text-xs text-mute">
                      {s.totalSets ?? 0} Sätze · {formatDurationLong(s.durationSec ?? 0)}
                    </div>
                  </div>
                  <span className="text-mute">›</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
