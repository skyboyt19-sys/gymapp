import { db, uid } from '../db/db'
import type { PRHistoryEntry, PersonalRecord, SetLog } from '../db/types'
import { epley1RM, setVolume } from './calc'

export type PRKind = 'weight' | 'e1rm' | 'volume' | 'reps'

export interface DetectedPR {
  exerciseId: string
  kind: PRKind
  value: number
  previous: number
}

const EMPTY = (exerciseId: string): PersonalRecord => ({
  id: `pr_${exerciseId}`,
  exerciseId,
  bestWeight: 0,
  bestE1rm: 0,
  bestVolume: 0,
  bestReps: 0,
  updatedAt: 0,
})

/**
 * Prüft einen gerade abgehakten Satz gegen die gespeicherten Rekorde
 * (die den Stand vor dieser Session abbilden) — für die Live-Meldung.
 */
export async function detectLivePRs(set: SetLog): Promise<DetectedPR[]> {
  if (!set.done || set.type === 'warmup') return []
  if (!set.weight || !set.reps) return []
  const rec = (await db.personalRecords.get(`pr_${set.exerciseId}`)) ?? EMPTY(set.exerciseId)
  const found: DetectedPR[] = []
  const e1 = epley1RM(set.weight, set.reps)
  if (set.weight > rec.bestWeight)
    found.push({ exerciseId: set.exerciseId, kind: 'weight', value: set.weight, previous: rec.bestWeight })
  if (e1 > rec.bestE1rm)
    found.push({ exerciseId: set.exerciseId, kind: 'e1rm', value: e1, previous: rec.bestE1rm })
  return found
}

/**
 * Rechnet die Rekorde für die angegebenen Übungen komplett neu aus allen
 * erledigten Sätzen — verlässlich auch nach dem Bearbeiten/Löschen alter Workouts.
 * Gibt die Rekorde zurück, die sich durch diese Session verbessert haben.
 */
export async function recomputePRs(exerciseIds: string[], sessionId?: string): Promise<DetectedPR[]> {
  const unique = [...new Set(exerciseIds)]
  const improved: DetectedPR[] = []

  for (const exerciseId of unique) {
    const before = (await db.personalRecords.get(`pr_${exerciseId}`)) ?? EMPTY(exerciseId)
    const sets = (await db.sets.where('exerciseId').equals(exerciseId).toArray()).filter(
      (s) => s.done && s.type !== 'warmup' && s.weight > 0 && s.reps > 0,
    )

    const next = EMPTY(exerciseId)
    next.updatedAt = Date.now()

    // Volumen pro Session aufsummieren
    const volPerSession = new Map<string, number>()
    for (const s of sets) {
      if (s.weight > next.bestWeight) {
        next.bestWeight = s.weight
        next.bestWeightAt = s.createdAt
        next.bestWeightReps = s.reps
      }
      const e1 = epley1RM(s.weight, s.reps)
      if (e1 > next.bestE1rm) {
        next.bestE1rm = e1
        next.bestE1rmAt = s.createdAt
      }
      if (s.reps > next.bestReps) {
        next.bestReps = s.reps
        next.bestRepsAt = s.createdAt
      }
      volPerSession.set(s.sessionId, (volPerSession.get(s.sessionId) ?? 0) + setVolume(s))
    }
    for (const [sid, vol] of volPerSession) {
      if (vol > next.bestVolume) {
        next.bestVolume = vol
        const first = sets.find((s) => s.sessionId === sid)
        next.bestVolumeAt = first?.createdAt
      }
    }

    if (sets.length === 0) {
      await db.personalRecords.delete(`pr_${exerciseId}`)
    } else {
      await db.personalRecords.put(next)
    }

    if (sessionId) {
      const kinds: Array<[PRKind, number, number]> = [
        ['weight', next.bestWeight, before.bestWeight],
        ['e1rm', next.bestE1rm, before.bestE1rm],
        ['volume', next.bestVolume, before.bestVolume],
        ['reps', next.bestReps, before.bestReps],
      ]
      for (const [kind, value, previous] of kinds) {
        if (value > previous + 1e-9) {
          improved.push({ exerciseId, kind, value, previous })
          const entry: PRHistoryEntry = {
            id: uid('prh'),
            exerciseId,
            sessionId,
            kind,
            value,
            at: Date.now(),
          }
          await db.prHistory.add(entry)
        }
      }
    }
  }
  return improved
}

/** Rekorde für alle Übungen neu berechnen (z. B. nach einem Import). */
export async function recomputeAllPRs(): Promise<void> {
  const ids = await db.sets.orderBy('exerciseId').uniqueKeys()
  await db.personalRecords.clear()
  await recomputePRs(ids as string[])
}

export const PR_LABEL: Record<PRKind, string> = {
  weight: 'Bestes Gewicht',
  e1rm: 'Bestes 1RM',
  volume: 'Bestes Volumen',
  reps: 'Meiste Wdh.',
}
