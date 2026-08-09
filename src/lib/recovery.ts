import type { Exercise, MuscleGroup, SetLog, WorkoutSession } from '../db/types'
import { MUSCLE_GROUPS } from '../db/types'

/** Stunden bis eine Muskelgruppe nach voller Belastung wieder als erholt gilt. */
const FULL_RECOVERY_HOURS = 48
const HEAVY_RECOVERY_HOURS = 72

export interface MuscleRecovery {
  muscle: MuscleGroup
  /** 0 = frisch belastet, 1 = vollständig erholt */
  recovery: number
  lastTrainedAt?: number
  lastSets: number
}

/**
 * Einfaches Modell: jede Muskelgruppe erholt sich linear über 48–72 h,
 * abhängig vom Satz-Umfang der letzten Belastung. Sekundäre Muskeln zählen halb.
 */
export function computeRecovery(
  sessions: WorkoutSession[],
  sets: SetLog[],
  exercises: Map<string, Exercise>,
  now = Date.now(),
): MuscleRecovery[] {
  const sessionById = new Map(sessions.map((s) => [s.id, s]))
  // Pro Muskel: Belastungen der letzten 5 Tage sammeln
  const load = new Map<MuscleGroup, { at: number; sets: number }[]>()

  for (const set of sets) {
    if (!set.done) continue
    const session = sessionById.get(set.sessionId)
    if (!session) continue
    const at = session.endedAt ?? session.startedAt
    if (now - at > 5 * 86400_000) continue
    const ex = exercises.get(set.exerciseId)
    if (!ex) continue
    const add = (m: MuscleGroup, weight: number) => {
      const arr = load.get(m) ?? []
      const last = arr.find((e) => e.at === at)
      if (last) last.sets += weight
      else arr.push({ at, sets: weight })
      load.set(m, arr)
    }
    add(ex.primary, set.type === 'warmup' ? 0.3 : 1)
    for (const s of ex.secondary) add(s, set.type === 'warmup' ? 0.15 : 0.5)
  }

  return MUSCLE_GROUPS.map((muscle) => {
    const entries = load.get(muscle) ?? []
    if (entries.length === 0) return { muscle, recovery: 1, lastSets: 0 }
    // Fatigue aller Einheiten aufaddieren, je nach vergangener Zeit abklingend
    let fatigue = 0
    let lastTrainedAt = 0
    let lastSets = 0
    for (const e of entries) {
      const hours = (now - e.at) / 3600_000
      const window = e.sets >= 8 ? HEAVY_RECOVERY_HOURS : FULL_RECOVERY_HOURS
      const remaining = Math.max(0, 1 - hours / window)
      const intensity = Math.min(1, e.sets / 10)
      fatigue += remaining * intensity
      if (e.at > lastTrainedAt) {
        lastTrainedAt = e.at
        lastSets = Math.round(e.sets)
      }
    }
    return {
      muscle,
      recovery: Math.max(0, Math.min(1, 1 - fatigue)),
      lastTrainedAt: lastTrainedAt || undefined,
      lastSets,
    }
  })
}

export function recoveryColor(r: number): string {
  if (r >= 0.85) return '#22c55e'
  if (r >= 0.6) return '#84cc16'
  if (r >= 0.35) return '#eab308'
  if (r >= 0.15) return '#f97316'
  return '#ef4444'
}

export function recoveryLabel(r: number): string {
  if (r >= 0.85) return 'Erholt'
  if (r >= 0.6) return 'Fast erholt'
  if (r >= 0.35) return 'Teilweise'
  if (r >= 0.15) return 'Ermüdet'
  return 'Stark ermüdet'
}
