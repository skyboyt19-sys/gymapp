import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { haptic } from '../lib/feedback'

export function Screen({
  title,
  subtitle,
  right,
  children,
  padded = true,
}: {
  title?: string
  subtitle?: string
  right?: ReactNode
  children: ReactNode
  padded?: boolean
}) {
  return (
    <div className="animate-page min-h-full">
      {title && (
        <header className="safe-top sticky top-0 z-20 bg-black/85 backdrop-blur-xl px-4 pb-3">
          <div className="flex items-end justify-between gap-3">
            <div className="min-w-0">
              <h1 className="text-[28px] font-bold tracking-tight truncate">{title}</h1>
              {subtitle && <p className="text-sm text-mute mt-0.5">{subtitle}</p>}
            </div>
            {right && <div className="shrink-0 pb-1">{right}</div>}
          </div>
        </header>
      )}
      <div className={padded ? 'px-4 pb-tab' : 'pb-tab'}>{children}</div>
    </div>
  )
}

/** Kopfzeile für Unterseiten: Zurück-Pfeil, Titel, optionale Aktion rechts. */
export function NavHeader({
  title,
  onBack,
  right,
  backLabel = 'Zurück',
}: {
  title: string
  onBack: () => void
  right?: ReactNode
  backLabel?: string
}) {
  return (
    <header className="safe-top sticky top-0 z-30 flex items-center gap-2 bg-black/85 px-2 pb-2 backdrop-blur-xl">
      <button className="flex items-center gap-0.5 px-2 py-2 text-brand font-medium" onClick={onBack}>
        <span className="text-xl leading-none">‹</span>
        <span className="text-[15px]">{backLabel}</span>
      </button>
      <h1 className="min-w-0 flex-1 truncate text-center text-[17px] font-semibold">{title}</h1>
      <div className="flex min-w-[76px] justify-end pr-1">{right}</div>
    </header>
  )
}

export function Section({
  title,
  action,
  children,
  className = '',
}: {
  title?: string
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`mt-6 ${className}`}>
      {(title || action) && (
        <div className="flex items-center justify-between mb-2 px-1">
          {title && <h2 className="label">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  )
}

export function EmptyState({
  icon,
  title,
  message,
  action,
}: {
  icon: string
  title: string
  message?: string
  action?: ReactNode
}) {
  return (
    <div className="card p-8 text-center">
      <div className="text-4xl mb-3">{icon}</div>
      <p className="font-semibold">{title}</p>
      {message && <p className="text-sm text-mute mt-1.5 leading-relaxed">{message}</p>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  )
}

/** Bottom-Sheet im iOS-Stil. */
export function Sheet({
  open,
  onClose,
  title,
  children,
  footer,
  full = false,
}: {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
  footer?: ReactNode
  full?: boolean
}) {
  useEffect(() => {
    if (!open) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [open])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex flex-col justify-end">
      <button
        aria-label="Schließen"
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
      />
      <div
        className={`animate-sheet relative flex flex-col rounded-t-3xl bg-ink-900 border-t border-ink-700 ${
          full ? 'h-[92vh]' : 'max-h-[86vh]'
        }`}
      >
        <div className="flex items-center justify-between px-4 pt-3 pb-2 border-b border-ink-800">
          <div className="w-16" />
          <h3 className="font-semibold truncate">{title}</h3>
          <button className="w-16 text-right text-brand font-medium py-2" onClick={onClose}>
            Fertig
          </button>
        </div>
        <div className="scroll-y flex-1 px-4 py-4">{children}</div>
        {footer && (
          <div
            className="px-4 pt-3 border-t border-ink-800 bg-ink-900"
            style={{ paddingBottom: 'calc(var(--safe-bottom) + 12px)' }}
          >
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Löschen',
  destructive = true,
  onConfirm,
  onCancel,
}: {
  open: boolean
  title: string
  message?: string
  confirmLabel?: string
  destructive?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-6">
      <button aria-label="Abbrechen" className="absolute inset-0 bg-black/70" onClick={onCancel} />
      <div className="card relative w-full max-w-sm p-5 bg-ink-850">
        <h3 className="text-lg font-semibold">{title}</h3>
        {message && <p className="text-sm text-mute mt-2 leading-relaxed">{message}</p>}
        <div className="mt-5 flex gap-3">
          <button className="btn-secondary flex-1" onClick={onCancel}>
            Abbrechen
          </button>
          <button
            className={destructive ? 'btn-danger flex-1' : 'btn-primary flex-1'}
            onClick={() => {
              haptic('warn')
              onConfirm()
            }}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

export function Stepper({
  value,
  onChange,
  step = 1,
  min = 0,
  max = 9999,
  suffix,
  decimals = 0,
  label,
}: {
  value: number
  onChange: (v: number) => void
  step?: number
  min?: number
  max?: number
  suffix?: string
  decimals?: number
  label?: string
}) {
  const clamp = (v: number) => Math.min(max, Math.max(min, Math.round(v * 1000) / 1000))
  return (
    <div>
      {label && <div className="label mb-1.5">{label}</div>}
      <div className="flex items-center gap-2">
        <button
          className="btn-secondary w-12 text-xl"
          onClick={() => {
            haptic()
            onChange(clamp(value - step))
          }}
        >
          −
        </button>
        <div className="flex-1 text-center tnum text-xl font-semibold">
          {value.toFixed(decimals)}
          {suffix && <span className="text-mute text-base ml-1">{suffix}</span>}
        </div>
        <button
          className="btn-secondary w-12 text-xl"
          onClick={() => {
            haptic()
            onChange(clamp(value + step))
          }}
        >
          +
        </button>
      </div>
    </div>
  )
}

/**
 * Zahlenfeld, das während der Eingabe den Rohtext behält (damit „12." oder ein
 * leeres Feld beim Tippen nicht sofort auf 0 zurückspringt).
 */
export function NumberField({
  value,
  onCommit,
  placeholder,
  className = '',
  decimals = 2,
  ariaLabel,
}: {
  value: number
  onCommit: (v: number) => void
  placeholder?: string
  className?: string
  decimals?: number
  ariaLabel?: string
}) {
  const [text, setText] = useState<string | null>(null)
  const ref = useRef<HTMLInputElement>(null)
  const display =
    text ?? (value === 0 ? '' : String(Math.round(value * 10 ** decimals) / 10 ** decimals))

  return (
    <input
      ref={ref}
      aria-label={ariaLabel}
      inputMode="decimal"
      enterKeyHint="done"
      className={className}
      placeholder={placeholder}
      value={display}
      onChange={(e) => setText(e.target.value.replace(',', '.'))}
      onFocus={(e) => e.currentTarget.select()}
      onBlur={() => {
        if (text !== null) {
          const n = parseFloat(text)
          onCommit(isFinite(n) && n >= 0 ? n : 0)
          setText(null)
        }
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter') ref.current?.blur()
      }}
    />
  )
}

export function Toggle({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  label: string
  hint?: string
}) {
  return (
    <button
      className="flex w-full items-center justify-between gap-4 py-3.5 text-left"
      onClick={() => {
        haptic()
        onChange(!checked)
      }}
    >
      <span className="min-w-0">
        <span className="block">{label}</span>
        {hint && <span className="block text-xs text-mute mt-0.5 leading-snug">{hint}</span>}
      </span>
      <span
        className={`relative h-[31px] w-[51px] shrink-0 rounded-full transition-colors ${
          checked ? 'bg-green-500' : 'bg-ink-600'
        }`}
      >
        <span
          className={`absolute top-[2px] h-[27px] w-[27px] rounded-full bg-white shadow transition-transform ${
            checked ? 'translate-x-[22px]' : 'translate-x-[2px]'
          }`}
        />
      </span>
    </button>
  )
}

export function Row({
  onClick,
  children,
  chevron = false,
  className = '',
}: {
  onClick?: () => void
  children: ReactNode
  chevron?: boolean
  className?: string
}) {
  const inner = (
    <div className={`flex items-center gap-3 px-4 py-3.5 ${className}`}>
      <div className="min-w-0 flex-1">{children}</div>
      {chevron && <span className="text-mute text-lg shrink-0">›</span>}
    </div>
  )
  if (!onClick) return inner
  return (
    <button className="block w-full text-left active:bg-ink-800 transition-colors" onClick={onClick}>
      {inner}
    </button>
  )
}

export function Divider() {
  return <div className="h-px bg-ink-700 ml-4" />
}

export function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="card p-3.5">
      <div className="label">{label}</div>
      <div className="text-xl font-bold mt-1 tnum">{value}</div>
      {hint && <div className="text-xs text-mute mt-0.5">{hint}</div>}
    </div>
  )
}

export function Pill({ children, tone = 'default' }: { children: ReactNode; tone?: 'default' | 'accent' | 'warn' }) {
  const tones = {
    default: 'bg-ink-700 text-mute',
    accent: 'bg-brand/20 text-brand',
    warn: 'bg-amber-500/15 text-amber-400',
  }
  return <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-medium ${tones[tone]}`}>{children}</span>
}
