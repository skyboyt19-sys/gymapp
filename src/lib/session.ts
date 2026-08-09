import { db } from '../db/db'
import { setVolume } from './calc'
import { recomputePRs } from './pr'

/**
 * Rechnet Kennzahlen einer gespeicherten Session neu und aktualisiert die
 * Rekorde der betroffenen Übungen. Nach jeder Bearbeitung eines alten Workouts
 * aufrufen, damit Statistik und PRs konsistent bleiben.
 */
export async function recalcSession(sessionId: string): Promise<void> {
  const session = await db.sessions.get(sessionId)
  if (!session) return
  const sets = await db.sets.where('sessionId').equals(sessionId).toArray()
  const done = sets.filter((s) => s.done)
  const order = session.exerciseOrder.filter((id) => sets.some((s) => s.exerciseId === id))
  for (const s of sets) if (!order.includes(s.exerciseId)) order.push(s.exerciseId)

  await db.sessions.update(sessionId, {
    totalVolume: done.reduce((a, s) => a + setVolume(s), 0),
    totalSets: done.length,
    exerciseOrder: order,
  })
  await recomputePRs([...new Set(sets.map((s) => s.exerciseId))])
}

/** Löscht eine Session inklusive Sätze und PR-Einträge und aktualisiert die Rekorde. */
export async function deleteSession(sessionId: string): Promise<void> {
  const sets = await db.sets.where('sessionId').equals(sessionId).toArray()
  const exerciseIds = [...new Set(sets.map((s) => s.exerciseId))]
  await db.sets.where('sessionId').equals(sessionId).delete()
  await db.prHistory.where('sessionId').equals(sessionId).delete()
  await db.sessions.delete(sessionId)
  await recomputePRs(exerciseIds)
}
