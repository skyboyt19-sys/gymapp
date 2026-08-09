import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useLiveQuery } from 'dexie-react-hooks'
import { DEFAULT_SETTINGS, db, initDb, requestPersistentStorage } from '../db/db'
import type { Settings } from '../db/types'
import { setFeedbackPrefs, unlockAudio } from '../lib/feedback'

export interface Toast {
  id: number
  title: string
  message?: string
  kind: 'info' | 'success' | 'error' | 'pr' | 'achievement'
}

interface AppStateValue {
  ready: boolean
  settings: Settings
  updateSettings: (patch: Partial<Settings>) => Promise<void>
  toasts: Toast[]
  pushToast: (t: Omit<Toast, 'id'>) => void
  dismissToast: (id: number) => void
}

const Ctx = createContext<AppStateValue | null>(null)

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false)
  const [toasts, setToasts] = useState<Toast[]>([])
  const toastId = useRef(1)

  const settings = useLiveQuery(async () => (await db.settings.get('settings')) ?? DEFAULT_SETTINGS, [], DEFAULT_SETTINGS)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      await initDb()
      const persisted = await requestPersistentStorage()
      const current = await db.settings.get('settings')
      if (current && current.persistedStorage !== persisted) {
        await db.settings.put({ ...current, persistedStorage: persisted })
      }
      if (!cancelled) setReady(true)
    })().catch((err) => {
      console.error('Initialisierung fehlgeschlagen', err)
      if (!cancelled) setReady(true)
    })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    setFeedbackPrefs(settings.sound, settings.vibration)
  }, [settings.sound, settings.vibration])

  // Audio beim ersten Tap freischalten (iOS-Anforderung)
  useEffect(() => {
    const handler = () => {
      unlockAudio()
      window.removeEventListener('pointerdown', handler)
    }
    window.addEventListener('pointerdown', handler)
    return () => window.removeEventListener('pointerdown', handler)
  }, [])

  const updateSettings = useCallback(
    async (patch: Partial<Settings>) => {
      const current = (await db.settings.get('settings')) ?? DEFAULT_SETTINGS
      await db.settings.put({ ...current, ...patch, id: 'settings' })
    },
    [],
  )

  const dismissToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const pushToast = useCallback(
    (t: Omit<Toast, 'id'>) => {
      const id = toastId.current++
      setToasts((prev) => [...prev.slice(-2), { ...t, id }])
      setTimeout(() => dismissToast(id), t.kind === 'error' ? 5200 : 3600)
    },
    [dismissToast],
  )

  const value = useMemo<AppStateValue>(
    () => ({ ready, settings, updateSettings, toasts, pushToast, dismissToast }),
    [ready, settings, updateSettings, toasts, pushToast, dismissToast],
  )

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useApp(): AppStateValue {
  const v = useContext(Ctx)
  if (!v) throw new Error('useApp muss innerhalb von AppStateProvider verwendet werden')
  return v
}

export function useSettings(): Settings {
  return useApp().settings
}
