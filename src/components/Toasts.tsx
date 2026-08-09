import { useApp } from '../state/AppState'

const STYLES: Record<string, string> = {
  info: 'bg-ink-800 border-ink-600',
  success: 'bg-green-600/20 border-green-500/40',
  error: 'bg-red-600/20 border-red-500/40',
  pr: 'bg-amber-500/20 border-amber-400/50',
  achievement: 'bg-brand/20 border-brand/50',
}

const ICONS: Record<string, string> = {
  info: 'ℹ️',
  success: '✓',
  error: '⚠️',
  pr: '🏆',
  achievement: '🎖️',
}

export function Toasts() {
  const { toasts, dismissToast } = useApp()
  if (toasts.length === 0) return null

  return (
    <div
      className="pointer-events-none fixed inset-x-0 z-[70] flex flex-col items-center gap-2 px-4"
      style={{ top: 'calc(var(--safe-top) + 8px)' }}
    >
      {toasts.map((t) => (
        <button
          key={t.id}
          onClick={() => dismissToast(t.id)}
          className={`animate-toast pointer-events-auto w-full max-w-sm rounded-2xl border px-4 py-3 text-left backdrop-blur-xl shadow-lg ${
            STYLES[t.kind] ?? STYLES.info
          }`}
        >
          <div className="flex items-start gap-2.5">
            <span className="text-lg leading-none mt-0.5">{ICONS[t.kind] ?? ICONS.info}</span>
            <span className="min-w-0">
              <span className="block font-semibold text-sm">{t.title}</span>
              {t.message && <span className="block text-sm text-white/70 mt-0.5">{t.message}</span>}
            </span>
          </div>
        </button>
      ))}
    </div>
  )
}
