import { NavLink, useLocation } from 'react-router-dom'
import { haptic } from '../lib/feedback'

const TABS = [
  { to: '/', label: 'Start', icon: HomeIcon },
  { to: '/history', label: 'Verlauf', icon: HistoryIcon },
  { to: '/stats', label: 'Statistik', icon: StatsIcon },
  { to: '/exercises', label: 'Übungen', icon: DumbbellIcon },
  { to: '/settings', label: 'Mehr', icon: GearIcon },
]

export function TabBar() {
  const { pathname } = useLocation()
  // Im laufenden Workout stört die Tab-Bar — dort blenden wir sie aus.
  if (pathname.startsWith('/workout')) return null

  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-40 border-t border-ink-700 bg-black/90 backdrop-blur-xl"
      style={{ paddingBottom: 'var(--safe-bottom)' }}
    >
      <ul className="flex" style={{ height: 'var(--tabbar-h)' }}>
        {TABS.map(({ to, label, icon: Icon }) => (
          <li key={to} className="flex-1">
            <NavLink
              to={to}
              end={to === '/'}
              onClick={() => haptic()}
              className={({ isActive }) =>
                `flex h-full flex-col items-center justify-center gap-[3px] text-[10px] font-medium transition-colors ${
                  isActive ? 'text-white' : 'text-mute'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <Icon active={isActive} />
                  <span>{label}</span>
                </>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}

type IconProps = { active?: boolean }

function base(active?: boolean) {
  return {
    width: 23,
    height: 23,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: active ? 2.4 : 1.9,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
  }
}

function HomeIcon({ active }: IconProps) {
  return (
    <svg {...base(active)}>
      <path d="M3 10.5 12 3l9 7.5" />
      <path d="M5.5 9.5V20h13V9.5" />
    </svg>
  )
}

function HistoryIcon({ active }: IconProps) {
  return (
    <svg {...base(active)}>
      <rect x="3" y="4.5" width="18" height="16" rx="3" />
      <path d="M3 9.5h18M8 3v3M16 3v3" />
    </svg>
  )
}

function StatsIcon({ active }: IconProps) {
  return (
    <svg {...base(active)}>
      <path d="M4 20V11M10 20V5M16 20v-6M22 20H2" />
    </svg>
  )
}

function DumbbellIcon({ active }: IconProps) {
  return (
    <svg {...base(active)}>
      <path d="M6.5 8v8M10 6.5v11M14 6.5v11M17.5 8v8M10 12h4M3.5 10.5v3M20.5 10.5v3" />
    </svg>
  )
}

function GearIcon({ active }: IconProps) {
  return (
    <svg {...base(active)}>
      <circle cx="12" cy="12" r="3.2" />
      <path d="M12 2.8v2.4M12 18.8v2.4M4.5 4.5l1.7 1.7M17.8 17.8l1.7 1.7M2.8 12h2.4M18.8 12h2.4M4.5 19.5l1.7-1.7M17.8 6.2l1.7-1.7" />
    </svg>
  )
}
