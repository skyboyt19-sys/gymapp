import { useNavigate } from 'react-router-dom'
import { useLiveQuery } from 'dexie-react-hooks'
import { db } from '../db/db'
import { NavHeader, StatTile } from '../components/ui'
import { ACHIEVEMENTS, buildAchievementContext } from '../lib/achievements'

export default function Achievements() {
  const navigate = useNavigate()

  const data = useLiveQuery(async () => {
    const unlocked = new Map((await db.achievements.toArray()).map((a) => [a.key, a.unlockedAt]))
    const ctx = await buildAchievementContext()
    return { unlocked, ctx }
  }, [])

  if (!data) return <div className="safe-top px-4 pt-10 text-center text-mute">Lädt…</div>

  const { unlocked, ctx } = data
  const list = ACHIEVEMENTS.map((def) => ({
    def,
    unlockedAt: unlocked.get(def.key),
    progress: def.goal?.(ctx),
  })).sort((a, b) => Number(!!b.unlockedAt) - Number(!!a.unlockedAt))

  return (
    <div className="animate-page min-h-full">
      <NavHeader title="Erfolge" backLabel="Start" onBack={() => navigate('/')} />

      <div className="px-4 pb-tab">
        <div className="mt-3 grid grid-cols-3 gap-3">
          <StatTile label="Freigeschaltet" value={`${unlocked.size}/${ACHIEVEMENTS.length}`} />
          <StatTile label="Serie" value={`${ctx.weekStreak} Wo.`} />
          <StatTile label="Rekorde" value={`${ctx.prCount}`} />
        </div>

        <div className="mt-5 space-y-2.5">
          {list.map(({ def, unlockedAt, progress }) => {
            const done = !!unlockedAt
            const pct = progress ? Math.min(100, Math.round((progress.current / progress.target) * 100)) : 0
            return (
              <div
                key={def.key}
                className={`card p-4 ${done ? '' : 'opacity-70'}`}
              >
                <div className="flex items-start gap-3">
                  <span className={`text-2xl ${done ? '' : 'grayscale'}`}>{def.icon}</span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="font-semibold">{def.title}</span>
                      {done && (
                        <span className="shrink-0 text-[11px] text-mute">
                          {new Date(unlockedAt).toLocaleDateString('de-DE')}
                        </span>
                      )}
                    </div>
                    <p className="mt-0.5 text-sm text-mute">{def.description}</p>
                    {!done && progress && (
                      <div className="mt-2">
                        <div className="h-1.5 overflow-hidden rounded-full bg-ink-700">
                          <div className="h-full rounded-full bg-brand" style={{ width: `${pct}%` }} />
                        </div>
                        <div className="mt-1 text-[11px] text-mute tnum">
                          {Math.min(progress.current, progress.target).toLocaleString('de-DE')} /{' '}
                          {progress.target.toLocaleString('de-DE')}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
