import { db, uid } from '../db/db'
import type { Category, Exercise, MuscleGroup, Program, Routine, RoutineExercise } from '../db/types'

export type Goal = 'Kraft' | 'Hypertrophie' | 'Ausdauer'

export interface GeneratorOptions {
  goal: Goal
  daysPerWeek: number
  equipment: Category[]
  name?: string
}

interface DayPlan {
  name: string
  /** Muskelgruppen in Trainingsreihenfolge; die erste ist der Schwerpunkt. */
  slots: MuscleGroup[]
}

const SPLITS: Record<number, DayPlan[]> = {
  1: [{ name: 'Ganzkörper', slots: ['Quadrizeps', 'Brust', 'Rücken', 'Schultern', 'Bauch'] }],
  2: [
    { name: 'Oberkörper', slots: ['Brust', 'Rücken', 'Schultern', 'Bizeps', 'Trizeps'] },
    { name: 'Unterkörper', slots: ['Quadrizeps', 'Hamstrings', 'Gesäß', 'Waden', 'Bauch'] },
  ],
  3: [
    { name: 'Push', slots: ['Brust', 'Schultern', 'Trizeps'] },
    { name: 'Pull', slots: ['Rücken', 'Bizeps', 'Unterarme'] },
    { name: 'Beine', slots: ['Quadrizeps', 'Hamstrings', 'Gesäß', 'Waden'] },
  ],
  4: [
    { name: 'Oberkörper A', slots: ['Brust', 'Rücken', 'Schultern', 'Trizeps'] },
    { name: 'Unterkörper A', slots: ['Quadrizeps', 'Hamstrings', 'Waden', 'Bauch'] },
    { name: 'Oberkörper B', slots: ['Rücken', 'Brust', 'Schultern', 'Bizeps'] },
    { name: 'Unterkörper B', slots: ['Hamstrings', 'Gesäß', 'Quadrizeps', 'Waden'] },
  ],
  5: [
    { name: 'Push', slots: ['Brust', 'Schultern', 'Trizeps'] },
    { name: 'Pull', slots: ['Rücken', 'Bizeps'] },
    { name: 'Beine', slots: ['Quadrizeps', 'Hamstrings', 'Waden'] },
    { name: 'Oberkörper', slots: ['Brust', 'Rücken', 'Schultern'] },
    { name: 'Beine & Bauch', slots: ['Gesäß', 'Hamstrings', 'Quadrizeps', 'Bauch'] },
  ],
  6: [
    { name: 'Push A', slots: ['Brust', 'Schultern', 'Trizeps'] },
    { name: 'Pull A', slots: ['Rücken', 'Bizeps'] },
    { name: 'Beine A', slots: ['Quadrizeps', 'Waden'] },
    { name: 'Push B', slots: ['Schultern', 'Brust', 'Trizeps'] },
    { name: 'Pull B', slots: ['Rücken', 'Bizeps', 'Unterarme'] },
    { name: 'Beine B', slots: ['Hamstrings', 'Gesäß', 'Waden'] },
  ],
  7: [
    { name: 'Push A', slots: ['Brust', 'Schultern', 'Trizeps'] },
    { name: 'Pull A', slots: ['Rücken', 'Bizeps'] },
    { name: 'Beine A', slots: ['Quadrizeps', 'Waden'] },
    { name: 'Push B', slots: ['Schultern', 'Brust', 'Trizeps'] },
    { name: 'Pull B', slots: ['Rücken', 'Bizeps'] },
    { name: 'Beine B', slots: ['Hamstrings', 'Gesäß', 'Waden'] },
    { name: 'Bauch & Cardio', slots: ['Bauch', 'Waden'] },
  ],
}

const GOAL_PARAMS: Record<Goal, { sets: number; reps: number; rest: number; perDay: number }> = {
  Kraft: { sets: 5, reps: 5, rest: 180, perDay: 5 },
  Hypertrophie: { sets: 4, reps: 10, rest: 105, perDay: 6 },
  Ausdauer: { sets: 3, reps: 16, rest: 60, perDay: 6 },
}

/** Grundübungen zuerst — je größer der Wert, desto früher im Workout. */
function priority(ex: Exercise): number {
  let score = 0
  if (ex.category === 'Langhantel') score += 4
  if (ex.category === 'Kurzhantel') score += 3
  if (ex.category === 'Maschine') score += 2
  if (ex.category === 'Kabel') score += 1
  if (ex.category === 'Körpergewicht') score += 1
  score += ex.secondary.length // Verbundübungen bevorzugen
  return score
}

export async function generateProgram(opts: GeneratorOptions): Promise<{ program: Program; routines: Routine[] }> {
  const days = Math.min(7, Math.max(1, Math.round(opts.daysPerWeek)))
  const plan = SPLITS[days] ?? SPLITS[3]
  const params = GOAL_PARAMS[opts.goal]
  const equipment = opts.equipment.length ? opts.equipment : (['Langhantel', 'Kurzhantel', 'Maschine', 'Kabel', 'Körpergewicht'] as Category[])

  const all = (await db.exercises.toArray()).filter(
    (e) => !e.archived && equipment.includes(e.category) && e.category !== 'Cardio',
  )

  const byMuscle = new Map<MuscleGroup, Exercise[]>()
  for (const ex of all) {
    const arr = byMuscle.get(ex.primary) ?? []
    arr.push(ex)
    byMuscle.set(ex.primary, arr)
  }
  for (const [, arr] of byMuscle) arr.sort((a, b) => priority(b) - priority(a) || a.name.localeCompare(b.name))

  const now = Date.now()
  const program: Program = {
    id: uid('prog'),
    name: opts.name?.trim() || `${opts.goal} · ${days}× pro Woche`,
    goal: opts.goal,
    daysPerWeek: days,
    notes: `Automatisch erzeugt am ${new Date().toLocaleDateString('de-DE')}.`,
    createdAt: now,
    updatedAt: now,
  }

  // Über alle Tage hinweg möglichst wenig wiederholen
  const usedGlobally = new Set<string>()
  const routines: Routine[] = plan.map((day, dayIndex) => {
    const picked: RoutineExercise[] = []
    const usedToday = new Set<string>()

    // Erst je Muskelgruppe eine Übung, dann Runde 2 für die Schwerpunkte
    for (let round = 0; round < 3 && picked.length < params.perDay; round++) {
      for (const muscle of day.slots) {
        if (picked.length >= params.perDay) break
        const candidates = byMuscle.get(muscle) ?? []
        const choice =
          candidates.find((c) => !usedToday.has(c.id) && !usedGlobally.has(c.id)) ??
          candidates.find((c) => !usedToday.has(c.id))
        if (!choice) continue
        usedToday.add(choice.id)
        usedGlobally.add(choice.id)
        picked.push({
          exerciseId: choice.id,
          targetSets: round === 0 ? params.sets : Math.max(3, params.sets - 1),
          targetReps: params.reps,
          targetSeconds: choice.timeBased ? 45 : undefined,
          restSec: params.rest,
        })
      }
    }

    return {
      id: uid('rt'),
      name: `${day.name}`,
      notes: `${opts.goal} · ${params.sets}×${params.reps}`,
      exercises: picked,
      programId: program.id,
      order: dayIndex,
      createdAt: now,
      updatedAt: now,
    }
  })

  await db.programs.add(program)
  await db.routines.bulkAdd(routines)
  return { program, routines }
}
