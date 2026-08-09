export const MUSCLE_GROUPS = [
  'Brust',
  'Rücken',
  'Schultern',
  'Bizeps',
  'Trizeps',
  'Quadrizeps',
  'Hamstrings',
  'Waden',
  'Gesäß',
  'Bauch',
  'Unterarme',
] as const

export type MuscleGroup = (typeof MUSCLE_GROUPS)[number]

export const CATEGORIES = [
  'Langhantel',
  'Kurzhantel',
  'Maschine',
  'Körpergewicht',
  'Kabel',
  'Cardio',
] as const

export type Category = (typeof CATEGORIES)[number]

export type Unit = 'kg' | 'lb'

export type SetType = 'normal' | 'warmup' | 'dropset'

export interface Exercise {
  id: string
  name: string
  /** Primäre Muskelgruppe (für Gruppierung/Statistik) */
  primary: MuscleGroup
  /** Zusätzlich beanspruchte Muskelgruppen */
  secondary: MuscleGroup[]
  category: Category
  /** Kurzanleitung / Ausführungstipp */
  instructions: string
  /** Standard-Pausenzeit in Sekunden */
  restSec: number
  /** true = Dauer statt Wiederholungen */
  timeBased: boolean
  /** true = selbst angelegt (kann gelöscht werden) */
  custom: boolean
  /** true = ausgeblendet (vordefinierte Übungen werden nie hart gelöscht) */
  archived?: boolean
  createdAt: number
  updatedAt: number
}

export interface RoutineExercise {
  exerciseId: string
  targetSets: number
  targetReps: number
  /** Ziel-Dauer in Sekunden bei zeitbasierten Übungen */
  targetSeconds?: number
  notes?: string
  restSec?: number
}

export interface Routine {
  id: string
  name: string
  notes?: string
  exercises: RoutineExercise[]
  programId?: string
  /** Position innerhalb eines Programms */
  order: number
  createdAt: number
  updatedAt: number
  lastPerformedAt?: number
}

export interface Program {
  id: string
  name: string
  goal?: 'Kraft' | 'Hypertrophie' | 'Ausdauer'
  daysPerWeek?: number
  notes?: string
  createdAt: number
  updatedAt: number
}

export interface WorkoutSession {
  id: string
  /** ISO-Datum (YYYY-MM-DD) des Starts, lokal */
  date: string
  startedAt: number
  endedAt?: number
  routineId?: string
  routineName?: string
  name: string
  notes?: string
  /** true solange das Workout läuft */
  active: boolean
  /** Reihenfolge der Übungen in dieser Session */
  exerciseOrder: string[]
  /** aufsummiert beim Beenden (kg-basiert, intern immer kg) */
  totalVolume?: number
  totalSets?: number
  durationSec?: number
}

export interface SetLog {
  id: string
  sessionId: string
  exerciseId: string
  setNumber: number
  /** Gewicht immer intern in kg gespeichert */
  weight: number
  reps: number
  /** Dauer in Sekunden bei zeitbasierten Übungen */
  seconds?: number
  rpe?: number
  type: SetType
  done: boolean
  createdAt: number
}

export interface BodyMetric {
  id: string
  date: string
  weight?: number
  bodyFat?: number
  chest?: number
  waist?: number
  hips?: number
  armLeft?: number
  armRight?: number
  thighLeft?: number
  thighRight?: number
  notes?: string
  createdAt: number
}

export interface PersonalRecord {
  id: string
  exerciseId: string
  bestWeight: number
  bestWeightAt?: number
  bestWeightReps?: number
  bestE1rm: number
  bestE1rmAt?: number
  bestVolume: number
  bestVolumeAt?: number
  bestReps: number
  bestRepsAt?: number
  updatedAt: number
}

export interface PRHistoryEntry {
  id: string
  exerciseId: string
  sessionId: string
  kind: 'weight' | 'e1rm' | 'volume' | 'reps'
  value: number
  at: number
}

export interface Achievement {
  id: string
  /** Schlüssel der Erfolgs-Definition */
  key: string
  unlockedAt: number
}

export interface Settings {
  id: 'settings'
  unit: Unit
  defaultRestSec: number
  restTimerAutoStart: boolean
  sound: boolean
  vibration: boolean
  theme: 'dark'
  /** Erinnerung an Backup nach x Tagen (0 = aus) */
  backupReminderDays: number
  lastBackupAt?: number
  barWeight: number
  /** Verfügbare Hantelscheiben (in kg) für den Plate-Rechner */
  plates: number[]
  weeklyGoal: number
  persistedStorage?: boolean
}

/** Snapshot-Format für Export/Import */
export interface BackupFile {
  format: 'lift-workout-tracker'
  version: number
  exportedAt: string
  counts: Record<string, number>
  data: {
    exercises: Exercise[]
    routines: Routine[]
    programs: Program[]
    sessions: WorkoutSession[]
    sets: SetLog[]
    bodyMetrics: BodyMetric[]
    personalRecords: PersonalRecord[]
    prHistory: PRHistoryEntry[]
    achievements: Achievement[]
    settings: Settings[]
  }
}
