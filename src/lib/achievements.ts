import { db, uid } from '../db/db'
import type { WorkoutSession } from '../db/types'
import { weekKey } from './format'

export interface AchievementDef {
  key: string
  title: string
  description: string
  icon: string
  /** Prüft, ob der Erfolg erreicht ist. */
  check: (ctx: AchievementContext) => boolean
  goal?: (ctx: AchievementContext) => { current: number; target: number }
}

export interface AchievementContext {
  sessions: WorkoutSession[]
  totalSets: number
  totalVolume: number
  weekStreak: number
  distinctExercises: number
  prCount: number
}

const workoutCountBadge = (n: number, title: string, icon: string): AchievementDef => ({
  key: `workouts_${n}`,
  title,
  description: `${n} Workouts abgeschlossen`,
  icon,
  check: (c) => c.sessions.length >= n,
  goal: (c) => ({ current: c.sessions.length, target: n }),
})

const volumeBadge = (t: number, title: string, icon: string): AchievementDef => ({
  key: `volume_${t}`,
  title,
  description: `${t.toLocaleString('de-DE')} kg Gesamtvolumen bewegt`,
  icon,
  check: (c) => c.totalVolume >= t,
  goal: (c) => ({ current: Math.round(c.totalVolume), target: t }),
})

const streakBadge = (n: number, title: string, icon: string): AchievementDef => ({
  key: `streak_${n}`,
  title,
  description: `${n} Wochen in Folge trainiert`,
  icon,
  check: (c) => c.weekStreak >= n,
  goal: (c) => ({ current: c.weekStreak, target: n }),
})

export const ACHIEVEMENTS: AchievementDef[] = [
  workoutCountBadge(1, 'Der Anfang', '🚀'),
  workoutCountBadge(5, 'Warmgelaufen', '🔥'),
  workoutCountBadge(10, 'Zweistellig', '💪'),
  workoutCountBadge(25, 'Stammgast', '🏋️'),
  workoutCountBadge(50, 'Halbes Hundert', '🥉'),
  workoutCountBadge(100, 'Hundert Workouts', '🥈'),
  workoutCountBadge(250, 'Eisenveteran', '🥇'),
  volumeBadge(10_000, '10 Tonnen', '⚙️'),
  volumeBadge(100_000, '100 Tonnen', '🛠️'),
  volumeBadge(500_000, '500 Tonnen', '🏭'),
  volumeBadge(1_000_000, 'Eine Million Kilo', '🌍'),
  streakBadge(2, 'Dranbleiben', '📈'),
  streakBadge(4, 'Ein Monat Serie', '🗓️'),
  streakBadge(12, 'Ein Quartal Serie', '🏆'),
  streakBadge(26, 'Ein halbes Jahr', '👑'),
  {
    key: 'sets_500',
    title: '500 Sätze',
    description: '500 Sätze protokolliert',
    icon: '📊',
    check: (c) => c.totalSets >= 500,
    goal: (c) => ({ current: c.totalSets, target: 500 }),
  },
  {
    key: 'exercises_25',
    title: 'Abwechslung',
    description: '25 verschiedene Übungen ausprobiert',
    icon: '🎯',
    check: (c) => c.distinctExercises >= 25,
    goal: (c) => ({ current: c.distinctExercises, target: 25 }),
  },
  {
    key: 'pr_10',
    title: 'Rekordjäger',
    description: '10 persönliche Rekorde aufgestellt',
    icon: '⭐',
    check: (c) => c.prCount >= 10,
    goal: (c) => ({ current: c.prCount, target: 10 }),
  },
  {
    key: 'early_bird',
    title: 'Frühaufsteher',
    description: 'Ein Workout vor 7 Uhr gestartet',
    icon: '🌅',
    check: (c) => c.sessions.some((s) => new Date(s.startedAt).getHours() < 7),
  },
  {
    key: 'night_owl',
    title: 'Nachteule',
    description: 'Ein Workout nach 22 Uhr gestartet',
    icon: '🌙',
    check: (c) => c.sessions.some((s) => new Date(s.startedAt).getHours() >= 22),
  },
  {
    key: 'marathon',
    title: 'Langer Atem',
    description: 'Ein Workout über 90 Minuten',
    icon: '⏱️',
    check: (c) => c.sessions.some((s) => (s.durationSec ?? 0) >= 90 * 60),
  },
]

/** Zusammenhängende Wochen mit mindestens einem Workout (inkl. aktueller Woche). */
export function computeWeekStreak(sessions: WorkoutSession[]): number {
  if (sessions.length === 0) return 0
  const weeks = new Set(sessions.map((s) => weekKey(new Date(s.startedAt))))
  let streak = 0
  const cursor = new Date()
  // Läuft die aktuelle Woche noch ohne Workout, zählen wir ab der Vorwoche.
  if (!weeks.has(weekKey(cursor))) cursor.setDate(cursor.getDate() - 7)
  for (;;) {
    if (weeks.has(weekKey(cursor))) {
      streak++
      cursor.setDate(cursor.getDate() - 7)
    } else break
    if (streak > 520) break
  }
  return streak
}

export async function buildAchievementContext(): Promise<AchievementContext> {
  const sessions = (await db.sessions.toArray()).filter((s) => !s.active)
  const sets = await db.sets.toArray()
  const done = sets.filter((s) => s.done)
  return {
    sessions,
    totalSets: done.length,
    totalVolume: done.reduce((a, s) => a + (s.weight || 0) * (s.reps || 0), 0),
    weekStreak: computeWeekStreak(sessions),
    distinctExercises: new Set(done.map((s) => s.exerciseId)).size,
    prCount: await db.prHistory.count(),
  }
}

/** Neue Erfolge freischalten und zurückgeben. */
export async function unlockAchievements(): Promise<AchievementDef[]> {
  const ctx = await buildAchievementContext()
  const existing = new Set((await db.achievements.toArray()).map((a) => a.key))
  const fresh: AchievementDef[] = []
  for (const def of ACHIEVEMENTS) {
    if (existing.has(def.key)) continue
    if (def.check(ctx)) {
      await db.achievements.add({ id: uid('ach'), key: def.key, unlockedAt: Date.now() })
      fresh.push(def)
    }
  }
  return fresh
}
