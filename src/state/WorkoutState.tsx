import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useLiveQuery } from 'dexie-react-hooks'
import { db, uid } from '../db/db'
import type { Exercise, SetLog, SetType, WorkoutSession } from '../db/types'
import { todayISO } from '../lib/format'
import { cue } from '../lib/feedback'
import { detectLivePRs, recomputePRs } from '../lib/pr'
import type { DetectedPR } from '../lib/pr'
import { unlockAchievements } from '../lib/achievements'
import type { AchievementDef } from '../lib/achievements'
import { setVolume } from '../lib/calc'
import { useApp } from './AppState'

const REST_KEY = 'lift.rest'

export interface RestTimer {
  endsAt: number
  total: number
  exerciseId?: string
}

export interface FinishSummary {
  session: WorkoutSession
  sets: SetLog[]
  prs: DetectedPR[]
  achievements: AchievementDef[]
}

interface WorkoutValue {
  session: WorkoutSession | undefined
  sets: SetLog[]
  rest: RestTimer | null
  restRemaining: number
  startWorkout: (opts?: { routineId?: string; name?: string }) => Promise<string>
  finishWorkout: () => Promise<FinishSummary | null>
  discardWorkout: () => Promise<void>
  addExercise: (exerciseId: string | string[]) => Promise<void>
  removeExercise: (exerciseId: string) => Promise<void>
  reorderExercises: (order: string[]) => Promise<void>
  addSet: (exerciseId: string, init?: Partial<SetLog>) => Promise<void>
  updateSet: (id: string, patch: Partial<SetLog>) => Promise<void>
  removeSet: (id: string) => Promise<void>
  toggleSetDone: (id: string) => Promise<void>
  startRest: (seconds: number, exerciseId?: string) => void
  adjustRest: (deltaSeconds: number) => void
  skipRest: () => void
  updateSessionNotes: (notes: string) => Promise<void>
  renameSession: (name: string) => Promise<void>
}

const Ctx = createContext<WorkoutValue | null>(null)

function loadRest(): RestTimer | null {
  try {
    const raw = localStorage.getItem(REST_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as RestTimer
    if (!parsed?.endsAt || parsed.endsAt < Date.now()) return null
    return parsed
  } catch {
    return null
  }
}

function saveRest(r: RestTimer | null) {
  try {
    if (r) localStorage.setItem(REST_KEY, JSON.stringify(r))
    else localStorage.removeItem(REST_KEY)
  } catch {
    /* Private-Mode o. Ä. — Timer läuft dann nur im Speicher */
  }
}

export function WorkoutProvider({ children }: { children: ReactNode }) {
  const { settings, pushToast } = useApp()
  const [rest, setRest] = useState<RestTimer | null>(() => loadRest())
  const [now, setNow] = useState(() => Date.now())
  const firedRef = useRef<number | null>(null)

  const session = useLiveQuery(async () => {
    const active = await db.sessions.filter((s) => s.active).toArray()
    return active.sort((a, b) => b.startedAt - a.startedAt)[0]
  }, [])

  const sets = useLiveQuery(
    async () => {
      if (!session) return []
      return (await db.sets.where('sessionId').equals(session.id).toArray()).sort(
        (a, b) => a.createdAt - b.createdAt,
      )
    },
    [session?.id],
    [] as SetLog[],
  )

  // Ticker nur laufen lassen, solange eine Pause aktiv ist
  useEffect(() => {
    if (!rest) return
    const t = setInterval(() => setNow(Date.now()), 250)
    return () => clearInterval(t)
  }, [rest])

  const restRemaining = rest ? Math.max(0, Math.ceil((rest.endsAt - now) / 1000)) : 0

  useEffect(() => {
    if (!rest) return
    if (restRemaining > 0) {
      firedRef.current = null
      return
    }
    if (firedRef.current === rest.endsAt) return
    firedRef.current = rest.endsAt
    cue('restEnd')
    saveRest(null)
    setRest(null)
  }, [rest, restRemaining])

  const startRest = useCallback((seconds: number, exerciseId?: string) => {
    if (seconds <= 0) return
    const r: RestTimer = { endsAt: Date.now() + seconds * 1000, total: seconds, exerciseId }
    saveRest(r)
    setNow(Date.now())
    setRest(r)
  }, [])

  const skipRest = useCallback(() => {
    firedRef.current = null
    saveRest(null)
    setRest(null)
  }, [])

  const adjustRest = useCallback((delta: number) => {
    setRest((prev) => {
      if (!prev) return prev
      const endsAt = Math.max(Date.now() + 1000, prev.endsAt + delta * 1000)
      const next = { ...prev, endsAt, total: Math.max(prev.total + delta, 5) }
      saveRest(next)
      return next
    })
  }, [])

  const startWorkout = useCallback(
    async (opts?: { routineId?: string; name?: string }) => {
      const existing = await db.sessions.filter((s) => s.active).toArray()
      if (existing.length) return existing[0].id

      const routine = opts?.routineId ? await db.routines.get(opts.routineId) : undefined
      const id = uid('sess')
      const startedAt = Date.now()
      const newSession: WorkoutSession = {
        id,
        date: todayISO(),
        startedAt,
        routineId: routine?.id,
        routineName: routine?.name,
        name: opts?.name?.trim() || routine?.name || 'Freies Workout',
        active: true,
        exerciseOrder: routine?.exercises.map((e) => e.exerciseId) ?? [],
      }
      await db.sessions.add(newSession)

      if (routine) {
        const exs = await db.exercises.bulkGet(routine.exercises.map((e) => e.exerciseId))
        const byId = new Map(exs.filter(Boolean).map((e) => [e!.id, e!]))
        const rows: SetLog[] = []
        let seq = 0
        for (const re of routine.exercises) {
          const ex = byId.get(re.exerciseId)
          if (!ex) continue
          // Letzte Werte dieser Übung als Vorschlag übernehmen
          const previous = await lastSetsFor(re.exerciseId)
          for (let i = 0; i < Math.max(1, re.targetSets); i++) {
            const prev = previous[i] ?? previous[previous.length - 1]
            rows.push({
              id: uid('set'),
              sessionId: id,
              exerciseId: re.exerciseId,
              setNumber: i + 1,
              weight: prev?.weight ?? 0,
              reps: ex.timeBased ? 0 : (prev?.reps ?? re.targetReps),
              seconds: ex.timeBased ? (prev?.seconds ?? re.targetSeconds ?? 60) : undefined,
              type: 'normal',
              done: false,
              createdAt: startedAt + seq++,
            })
          }
        }
        if (rows.length) await db.sets.bulkAdd(rows)
        await db.routines.update(routine.id, { lastPerformedAt: startedAt })
      }
      return id
    },
    [],
  )

  const addExercise = useCallback(
    async (exerciseId: string | string[]) => {
      if (!session) return
      const ids = Array.isArray(exerciseId) ? exerciseId : [exerciseId]
      // Reihenfolge frisch aus der DB lesen — mehrere Aufrufe hintereinander
      // dürfen sich nicht gegenseitig überschreiben.
      const current = await db.sessions.get(session.id)
      if (!current) return
      const order = [...current.exerciseOrder]
      const rows: SetLog[] = []
      let seq = 0

      for (const id of ids) {
        if (order.includes(id)) continue
        order.push(id)
        const ex = await db.exercises.get(id)
        const previous = await lastSetsFor(id)
        const prev = previous[0]
        rows.push({
          id: uid('set'),
          sessionId: session.id,
          exerciseId: id,
          setNumber: 1,
          weight: prev?.weight ?? 0,
          reps: ex?.timeBased ? 0 : (prev?.reps ?? 10),
          seconds: ex?.timeBased ? (prev?.seconds ?? 60) : undefined,
          type: 'normal',
          done: false,
          createdAt: Date.now() + seq++,
        })
      }

      if (rows.length === 0) return
      await db.sets.bulkAdd(rows)
      await db.sessions.update(session.id, { exerciseOrder: order })
    },
    [session],
  )

  const removeExercise = useCallback(
    async (exerciseId: string) => {
      if (!session) return
      await db.sets.where({ sessionId: session.id, exerciseId }).delete()
      await db.sessions.update(session.id, {
        exerciseOrder: session.exerciseOrder.filter((id) => id !== exerciseId),
      })
    },
    [session],
  )

  const reorderExercises = useCallback(
    async (order: string[]) => {
      if (!session) return
      await db.sessions.update(session.id, { exerciseOrder: order })
    },
    [session],
  )

  const addSet = useCallback(
    async (exerciseId: string, init?: Partial<SetLog>) => {
      if (!session) return
      // Frisch aus der DB lesen, damit schnelles Doppeltippen keine
      // doppelte Satznummer erzeugt.
      const existing = (
        await db.sets.where({ sessionId: session.id, exerciseId }).toArray()
      ).sort((a, b) => a.createdAt - b.createdAt)
      const last = existing[existing.length - 1]
      await db.sets.add({
        id: uid('set'),
        sessionId: session.id,
        exerciseId,
        setNumber: existing.length + 1,
        weight: last?.weight ?? 0,
        reps: last?.reps ?? 10,
        seconds: last?.seconds,
        type: 'normal',
        done: false,
        createdAt: Date.now(),
        ...init,
      })
    },
    [session],
  )

  const updateSet = useCallback(async (id: string, patch: Partial<SetLog>) => {
    await db.sets.update(id, patch)
  }, [])

  const removeSet = useCallback(
    async (id: string) => {
      const target = sets.find((s) => s.id === id)
      await db.sets.delete(id)
      if (target) {
        // Satznummern der Übung neu durchzählen
        const rest = sets
          .filter((s) => s.exerciseId === target.exerciseId && s.id !== id)
          .sort((a, b) => a.createdAt - b.createdAt)
        await Promise.all(rest.map((s, i) => db.sets.update(s.id, { setNumber: i + 1 })))
      }
    },
    [sets],
  )

  const toggleSetDone = useCallback(
    async (id: string) => {
      const set = sets.find((s) => s.id === id)
      if (!set) return
      const done = !set.done
      await db.sets.update(id, { done })
      if (!done) return

      cue('setDone')

      const ex = await db.exercises.get(set.exerciseId)
      // Live-PR-Meldung
      const prs = await detectLivePRs({ ...set, done })
      for (const pr of prs) {
        if (pr.kind !== 'weight' && pr.kind !== 'e1rm') continue
        cue('pr')
        pushToast({
          kind: 'pr',
          title: pr.kind === 'weight' ? 'Neuer Gewichts-Rekord!' : 'Neues Bestes 1RM!',
          message: `${ex?.name ?? 'Übung'} · ${Math.round(pr.value * 10) / 10} kg`,
        })
        break
      }

      if (settings.restTimerAutoStart) {
        const seconds = ex?.restSec || settings.defaultRestSec
        startRest(seconds, set.exerciseId)
      }
    },
    [sets, settings.restTimerAutoStart, settings.defaultRestSec, pushToast, startRest],
  )

  const finishWorkout = useCallback(async (): Promise<FinishSummary | null> => {
    if (!session) return null
    const all = await db.sets.where('sessionId').equals(session.id).toArray()
    const done = all.filter((s) => s.done)

    // Nicht abgehakte Sätze verwerfen, damit die Statistik sauber bleibt
    const undone = all.filter((s) => !s.done)
    if (undone.length) await db.sets.bulkDelete(undone.map((s) => s.id))

    if (done.length === 0) {
      await db.sessions.delete(session.id)
      skipRest()
      return null
    }

    const endedAt = Date.now()
    const patch: Partial<WorkoutSession> = {
      active: false,
      endedAt,
      durationSec: Math.round((endedAt - session.startedAt) / 1000),
      totalVolume: done.reduce((a, s) => a + setVolume(s), 0),
      totalSets: done.length,
      exerciseOrder: session.exerciseOrder.filter((id) => done.some((s) => s.exerciseId === id)),
    }
    await db.sessions.update(session.id, patch)

    const prs = await recomputePRs([...new Set(done.map((s) => s.exerciseId))], session.id)
    const achievements = await unlockAchievements()
    skipRest()
    cue('finish')

    const finished = (await db.sessions.get(session.id))!
    return { session: finished, sets: done, prs, achievements }
  }, [session, skipRest])

  const discardWorkout = useCallback(async () => {
    if (!session) return
    await db.sets.where('sessionId').equals(session.id).delete()
    await db.sessions.delete(session.id)
    skipRest()
  }, [session, skipRest])

  const updateSessionNotes = useCallback(
    async (notes: string) => {
      if (!session) return
      await db.sessions.update(session.id, { notes })
    },
    [session],
  )

  const renameSession = useCallback(
    async (name: string) => {
      if (!session) return
      await db.sessions.update(session.id, { name })
    },
    [session],
  )

  const value = useMemo<WorkoutValue>(
    () => ({
      session,
      sets: sets ?? [],
      rest,
      restRemaining,
      startWorkout,
      finishWorkout,
      discardWorkout,
      addExercise,
      removeExercise,
      reorderExercises,
      addSet,
      updateSet,
      removeSet,
      toggleSetDone,
      startRest,
      adjustRest,
      skipRest,
      updateSessionNotes,
      renameSession,
    }),
    [
      session,
      sets,
      rest,
      restRemaining,
      startWorkout,
      finishWorkout,
      discardWorkout,
      addExercise,
      removeExercise,
      reorderExercises,
      addSet,
      updateSet,
      removeSet,
      toggleSetDone,
      startRest,
      adjustRest,
      skipRest,
      updateSessionNotes,
      renameSession,
    ],
  )

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useWorkout(): WorkoutValue {
  const v = useContext(Ctx)
  if (!v) throw new Error('useWorkout muss innerhalb von WorkoutProvider verwendet werden')
  return v
}

/** Sätze der letzten abgeschlossenen Einheit mit dieser Übung (als Vorschlag). */
export async function lastSetsFor(exerciseId: string): Promise<SetLog[]> {
  const rows = await db.sets.where('exerciseId').equals(exerciseId).toArray()
  const doneRows = rows.filter((s) => s.done)
  if (doneRows.length === 0) return []
  const sessions = await db.sessions.bulkGet([...new Set(doneRows.map((s) => s.sessionId))])
  const finished = sessions.filter((s): s is WorkoutSession => !!s && !s.active)
  if (finished.length === 0) return []
  const latest = finished.sort((a, b) => b.startedAt - a.startedAt)[0]
  return doneRows.filter((s) => s.sessionId === latest.id).sort((a, b) => a.setNumber - b.setNumber)
}

export async function exerciseMap(): Promise<Map<string, Exercise>> {
  return new Map((await db.exercises.toArray()).map((e) => [e.id, e]))
}

export type { SetType }
