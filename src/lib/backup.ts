import { db, DEFAULT_SETTINGS } from '../db/db'
import type { BackupFile } from '../db/types'
import { recomputeAllPRs } from './pr'

export const BACKUP_VERSION = 1

export async function buildBackup(): Promise<BackupFile> {
  const [
    exercises,
    routines,
    programs,
    sessions,
    sets,
    bodyMetrics,
    personalRecords,
    prHistory,
    achievements,
    settings,
  ] = await Promise.all([
    db.exercises.toArray(),
    db.routines.toArray(),
    db.programs.toArray(),
    db.sessions.toArray(),
    db.sets.toArray(),
    db.bodyMetrics.toArray(),
    db.personalRecords.toArray(),
    db.prHistory.toArray(),
    db.achievements.toArray(),
    db.settings.toArray(),
  ])

  return {
    format: 'lift-workout-tracker',
    version: BACKUP_VERSION,
    exportedAt: new Date().toISOString(),
    counts: {
      exercises: exercises.length,
      routines: routines.length,
      programs: programs.length,
      sessions: sessions.length,
      sets: sets.length,
      bodyMetrics: bodyMetrics.length,
    },
    data: {
      exercises,
      routines,
      programs,
      sessions,
      sets,
      bodyMetrics,
      personalRecords,
      prHistory,
      achievements,
      settings,
    },
  }
}

export function backupFilename(d = new Date()): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `lift-backup-${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}-${p(d.getHours())}${p(
    d.getMinutes(),
  )}.json`
}

/** Lädt das Backup als Datei herunter (iOS: landet in „Dateien"/Downloads). */
export async function downloadBackup(): Promise<{ filename: string; bytes: number }> {
  const backup = await buildBackup()
  const json = JSON.stringify(backup, null, 2)
  const blob = new Blob([json], { type: 'application/json' })
  const filename = backupFilename()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 10_000)

  const settings = (await db.settings.get('settings')) ?? DEFAULT_SETTINGS
  await db.settings.put({ ...settings, lastBackupAt: Date.now() })
  return { filename, bytes: blob.size }
}

/** Teilt das Backup über das iOS-Share-Sheet, falls verfügbar. */
export async function shareBackup(): Promise<boolean> {
  try {
    const backup = await buildBackup()
    const file = new File([JSON.stringify(backup, null, 2)], backupFilename(), {
      type: 'application/json',
    })
    const nav = navigator as Navigator & { canShare?: (d: ShareData) => boolean }
    if (!nav.share || !nav.canShare?.({ files: [file] })) return false
    await nav.share({ files: [file], title: 'Lift Backup' })
    const settings = (await db.settings.get('settings')) ?? DEFAULT_SETTINGS
    await db.settings.put({ ...settings, lastBackupAt: Date.now() })
    return true
  } catch {
    return false
  }
}

export function parseBackup(text: string): BackupFile {
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    throw new Error('Die Datei ist kein gültiges JSON.')
  }
  const b = parsed as Partial<BackupFile>
  if (!b || typeof b !== 'object' || b.format !== 'lift-workout-tracker' || !b.data) {
    throw new Error('Das ist keine Lift-Backup-Datei.')
  }
  if ((b.version ?? 0) > BACKUP_VERSION) {
    throw new Error('Das Backup stammt aus einer neueren App-Version.')
  }
  return b as BackupFile
}

export type ImportMode = 'replace' | 'merge'

export interface ImportResult {
  sessions: number
  sets: number
  exercises: number
  routines: number
  programs: number
  bodyMetrics: number
}

/**
 * Stellt ein Backup wieder her.
 * - `replace`: löscht alle vorhandenen Daten und schreibt das Backup.
 * - `merge`: ergänzt fehlende Datensätze, vorhandene IDs bleiben unangetastet.
 */
export async function restoreBackup(backup: BackupFile, mode: ImportMode): Promise<ImportResult> {
  const d = backup.data
  const tables = [
    db.exercises,
    db.routines,
    db.programs,
    db.sessions,
    db.sets,
    db.bodyMetrics,
    db.personalRecords,
    db.prHistory,
    db.achievements,
    db.settings,
  ]

  await db.transaction('rw', tables, async () => {
    if (mode === 'replace') {
      await Promise.all(tables.map((t) => t.clear()))
      await db.exercises.bulkPut(d.exercises ?? [])
      await db.routines.bulkPut(d.routines ?? [])
      await db.programs.bulkPut(d.programs ?? [])
      await db.sessions.bulkPut(d.sessions ?? [])
      await db.sets.bulkPut(d.sets ?? [])
      await db.bodyMetrics.bulkPut(d.bodyMetrics ?? [])
      await db.personalRecords.bulkPut(d.personalRecords ?? [])
      await db.prHistory.bulkPut(d.prHistory ?? [])
      await db.achievements.bulkPut(d.achievements ?? [])
      await db.settings.bulkPut(d.settings ?? [DEFAULT_SETTINGS])
    } else {
      const addMissing = async <T extends { id: string }>(
        table: { bulkGet: (k: string[]) => Promise<(T | undefined)[]>; bulkAdd: (v: T[]) => Promise<unknown> },
        rows: T[] | undefined,
      ) => {
        if (!rows?.length) return
        const have = new Set(
          (await table.bulkGet(rows.map((r) => r.id))).filter(Boolean).map((r) => (r as T).id),
        )
        const missing = rows.filter((r) => !have.has(r.id))
        if (missing.length) await table.bulkAdd(missing)
      }
      await addMissing(db.exercises, d.exercises)
      await addMissing(db.routines, d.routines)
      await addMissing(db.programs, d.programs)
      await addMissing(db.sessions, d.sessions)
      await addMissing(db.sets, d.sets)
      await addMissing(db.bodyMetrics, d.bodyMetrics)
      await addMissing(db.achievements, d.achievements)
      await addMissing(db.prHistory, d.prHistory)
    }
  })

  // Rekorde immer frisch aus den Sätzen ableiten — das ist die Quelle der Wahrheit.
  await recomputeAllPRs()

  return {
    sessions: d.sessions?.length ?? 0,
    sets: d.sets?.length ?? 0,
    exercises: d.exercises?.length ?? 0,
    routines: d.routines?.length ?? 0,
    programs: d.programs?.length ?? 0,
    bodyMetrics: d.bodyMetrics?.length ?? 0,
  }
}

export function daysSince(ts?: number): number | null {
  if (!ts) return null
  return Math.floor((Date.now() - ts) / 86400_000)
}
