import Dexie, { type Table } from 'dexie'
import { buildSeedExercises } from './seedExercises'
import type {
  Achievement,
  BodyMetric,
  Exercise,
  PRHistoryEntry,
  PersonalRecord,
  Program,
  Routine,
  SetLog,
  Settings,
  WorkoutSession,
} from './types'

export const DEFAULT_SETTINGS: Settings = {
  id: 'settings',
  unit: 'kg',
  defaultRestSec: 120,
  restTimerAutoStart: true,
  sound: true,
  vibration: true,
  theme: 'dark',
  backupReminderDays: 14,
  barWeight: 20,
  plates: [25, 20, 15, 10, 5, 2.5, 1.25],
  weeklyGoal: 4,
}

export class LiftDB extends Dexie {
  exercises!: Table<Exercise, string>
  routines!: Table<Routine, string>
  programs!: Table<Program, string>
  sessions!: Table<WorkoutSession, string>
  sets!: Table<SetLog, string>
  bodyMetrics!: Table<BodyMetric, string>
  personalRecords!: Table<PersonalRecord, string>
  prHistory!: Table<PRHistoryEntry, string>
  achievements!: Table<Achievement, string>
  settings!: Table<Settings, string>

  constructor() {
    super('lift-workout-tracker')
    this.version(1).stores({
      exercises: 'id, name, primary, category, custom, archived',
      routines: 'id, name, programId, order, updatedAt',
      programs: 'id, name, updatedAt',
      sessions: 'id, date, startedAt, active, routineId',
      sets: 'id, sessionId, exerciseId, [sessionId+exerciseId], createdAt',
      bodyMetrics: 'id, date',
      personalRecords: 'id, exerciseId',
      prHistory: 'id, exerciseId, sessionId, at',
      achievements: 'id, key',
      settings: 'id',
    })
  }
}

export const db = new LiftDB()

export function uid(prefix = 'id'): string {
  const rnd =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID().replace(/-/g, '').slice(0, 12)
      : Math.random().toString(36).slice(2, 14)
  return `${prefix}_${Date.now().toString(36)}${rnd}`
}

/**
 * Legt Standard-Einstellungen an und ergänzt fehlende vordefinierte Übungen.
 * Bestehende (auch bearbeitete) Übungen werden nie überschrieben.
 */
export async function initDb(): Promise<void> {
  const existingSettings = await db.settings.get('settings')
  if (!existingSettings) {
    await db.settings.put(DEFAULT_SETTINGS)
  } else {
    // Fehlende Felder aus späteren App-Versionen ergänzen
    await db.settings.put({ ...DEFAULT_SETTINGS, ...existingSettings })
  }

  const seeds = buildSeedExercises()
  const ids = seeds.map((e) => e.id)
  const present = new Set((await db.exercises.bulkGet(ids)).filter(Boolean).map((e) => e!.id))
  const missing = seeds.filter((e) => !present.has(e.id))
  if (missing.length) await db.exercises.bulkPut(missing)
}

/** Bittet iOS/Safari darum, den Speicher dauerhaft zu behalten. */
export async function requestPersistentStorage(): Promise<boolean> {
  try {
    if (!('storage' in navigator) || !navigator.storage?.persist) return false
    if (await navigator.storage.persisted()) return true
    return await navigator.storage.persist()
  } catch {
    return false
  }
}

export async function storageEstimate(): Promise<{ usage: number; quota: number } | null> {
  try {
    if (!navigator.storage?.estimate) return null
    const e = await navigator.storage.estimate()
    return { usage: e.usage ?? 0, quota: e.quota ?? 0 }
  } catch {
    return null
  }
}
