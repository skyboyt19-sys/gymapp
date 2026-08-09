import type { SetLog } from '../db/types'

/** Geschätztes 1RM nach Epley. Bei 1 Wdh. ist es einfach das Gewicht. */
export function epley1RM(weight: number, reps: number): number {
  if (!weight || !reps || reps < 1) return 0
  if (reps === 1) return weight
  return weight * (1 + reps / 30)
}

/** Volumen eines Satzes (Gewicht × Wdh.). Zeitbasierte Sätze zählen 0. */
export function setVolume(s: Pick<SetLog, 'weight' | 'reps'>): number {
  return (s.weight || 0) * (s.reps || 0)
}

export function totalVolume(sets: SetLog[]): number {
  return sets.reduce((sum, s) => sum + (s.done ? setVolume(s) : 0), 0)
}

export const KG_PER_LB = 0.45359237

export function kgToDisplay(kg: number, unit: 'kg' | 'lb'): number {
  return unit === 'kg' ? kg : kg / KG_PER_LB
}

export function displayToKg(value: number, unit: 'kg' | 'lb'): number {
  return unit === 'kg' ? value : value * KG_PER_LB
}

/** Rundet auf 2 Nachkommastellen und entfernt überflüssige Nullen. */
export function trimNum(n: number, digits = 2): string {
  if (!isFinite(n)) return '0'
  const r = Math.round(n * 10 ** digits) / 10 ** digits
  return String(r)
}

/**
 * Hantelscheiben-Rechner: welche Scheiben pro Seite ergeben das Zielgewicht?
 * Gibt zusätzlich das tatsächlich erreichbare Gewicht zurück.
 */
export function calcPlates(
  targetKg: number,
  barKg: number,
  availablePlates: number[],
): { plates: number[]; achievable: number; rest: number } {
  const perSide = (targetKg - barKg) / 2
  if (perSide <= 0) return { plates: [], achievable: barKg, rest: Math.max(0, targetKg - barKg) }
  const sorted = [...availablePlates].sort((a, b) => b - a)
  const plates: number[] = []
  let remaining = perSide
  for (const p of sorted) {
    while (remaining >= p - 1e-9) {
      plates.push(p)
      remaining -= p
      if (plates.length > 40) break
    }
  }
  const achievable = barKg + (perSide - remaining) * 2
  return { plates, achievable, rest: remaining * 2 }
}
