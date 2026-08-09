export function todayISO(d: Date = new Date()): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

export function parseISODate(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, (m ?? 1) - 1, d ?? 1)
}

export function formatDate(iso: string): string {
  return parseISODate(iso).toLocaleDateString('de-DE', {
    weekday: 'short',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

export function formatDateShort(iso: string): string {
  return parseISODate(iso).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })
}

export function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })
}

/** Sekunden -> "1:05" bzw. "1:02:03" */
export function formatDuration(totalSec: number): string {
  const s = Math.max(0, Math.round(totalSec))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  const p = (n: number) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${p(m)}:${p(sec)}` : `${m}:${p(sec)}`
}

/** Sekunden -> "1 Std 5 Min" / "45 Min" */
export function formatDurationLong(totalSec: number): string {
  const s = Math.max(0, Math.round(totalSec))
  const h = Math.floor(s / 3600)
  const m = Math.round((s % 3600) / 60)
  if (h > 0) return `${h} Std ${m} Min`
  if (m > 0) return `${m} Min`
  return `${s} Sek`
}

export function relativeDays(iso: string): string {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const d = parseISODate(iso)
  const diff = Math.round((today.getTime() - d.getTime()) / 86400000)
  if (diff === 0) return 'Heute'
  if (diff === 1) return 'Gestern'
  if (diff < 7) return `vor ${diff} Tagen`
  return formatDate(iso)
}

/** Montag der Woche, in der das Datum liegt (lokal). */
export function startOfWeek(d: Date): Date {
  const x = new Date(d)
  x.setHours(0, 0, 0, 0)
  const day = (x.getDay() + 6) % 7 // Mo = 0
  x.setDate(x.getDate() - day)
  return x
}

export function weekKey(d: Date): string {
  return todayISO(startOfWeek(d))
}

export function addDays(d: Date, n: number): Date {
  const x = new Date(d)
  x.setDate(x.getDate() + n)
  return x
}

export function daysBetween(a: Date, b: Date): number {
  const x = new Date(a)
  const y = new Date(b)
  x.setHours(0, 0, 0, 0)
  y.setHours(0, 0, 0, 0)
  return Math.round((y.getTime() - x.getTime()) / 86400000)
}
