import { formatDuration } from '../lib/format'
import { haptic } from '../lib/feedback'
import { useWorkout } from '../state/WorkoutState'

/** Schwebende Pausen-Anzeige mit Fortschrittsring, +/−15 s und Überspringen. */
export function RestTimerBar({ bottomOffset = 0 }: { bottomOffset?: number }) {
  const { rest, restRemaining, adjustRest, skipRest } = useWorkout()
  if (!rest) return null

  const progress = Math.max(0, Math.min(1, restRemaining / rest.total))
  const r = 16
  const circumference = 2 * Math.PI * r

  return (
    <div
      className="fixed inset-x-0 z-40 px-4"
      style={{ bottom: `calc(var(--safe-bottom) + ${bottomOffset}px + 12px)` }}
    >
      <div className="mx-auto flex max-w-md items-center gap-3 rounded-2xl border border-ink-600 bg-ink-850/95 px-3 py-2.5 backdrop-blur-xl shadow-xl">
        <svg width="40" height="40" viewBox="0 0 40 40" className="shrink-0 -rotate-90">
          <circle cx="20" cy="20" r={r} fill="none" stroke="#2a2a2e" strokeWidth="4" />
          <circle
            cx="20"
            cy="20"
            r={r}
            fill="none"
            stroke={restRemaining <= 5 ? '#f59e0b' : '#3b82f6'}
            strokeWidth="4"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={circumference * (1 - progress)}
            style={{ transition: 'stroke-dashoffset 0.25s linear' }}
          />
        </svg>

        <div className="min-w-0 flex-1">
          <div className="text-[11px] uppercase tracking-wider text-mute">Pause</div>
          <div className="text-2xl font-bold tnum leading-tight">{formatDuration(restRemaining)}</div>
        </div>

        <button
          className="btn-secondary px-2.5 text-sm"
          onClick={() => {
            haptic()
            adjustRest(-15)
          }}
        >
          −15
        </button>
        <button
          className="btn-secondary px-2.5 text-sm"
          onClick={() => {
            haptic()
            adjustRest(15)
          }}
        >
          +15
        </button>
        <button
          className="btn-primary px-3 text-sm"
          onClick={() => {
            haptic('warn')
            skipRest()
          }}
        >
          Skip
        </button>
      </div>
    </div>
  )
}
