import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

const AXIS = { stroke: '#8b8b93', fontSize: 11 }
const GRID = '#1d1d20'

/** 1615 -> "1,6k" — hält die Y-Achse schmal genug fürs iPhone. */
function compact(v: number): string {
  const n = Number(v)
  if (!isFinite(n)) return ''
  if (Math.abs(n) >= 1000) return `${(n / 1000).toFixed(n % 1000 === 0 ? 0 : 1).replace('.', ',')}k`
  return String(Math.round(n * 100) / 100)
}

const TOOLTIP_STYLE = {
  contentStyle: {
    background: '#151517',
    border: '1px solid #2a2a2e',
    borderRadius: 12,
    fontSize: 12,
    color: '#f5f5f7',
  },
  labelStyle: { color: '#8b8b93', marginBottom: 2 },
  itemStyle: { color: '#f5f5f7' },
}

export interface Point {
  label: string
  value: number
}

export function TrendChart({
  data,
  color = '#3b82f6',
  unit = '',
  height = 190,
  name = 'Wert',
}: {
  data: Point[]
  color?: string
  unit?: string
  height?: number
  name?: string
}) {
  if (data.length === 0) return <ChartEmpty />
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 10, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={`grad-${color.replace('#', '')}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.35} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={false} minTickGap={18} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} width={42} tickFormatter={compact} />
          <Tooltip {...TOOLTIP_STYLE} formatter={(v) => [`${Math.round(Number(v) * 10) / 10} ${unit}`, name]} />
          <Area
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={2.4}
            fill={`url(#grad-${color.replace('#', '')})`}
            dot={data.length <= 20 ? { r: 2.5, fill: color } : false}
            activeDot={{ r: 4 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

export function SimpleLineChart({
  data,
  color = '#22c55e',
  unit = '',
  height = 190,
  name = 'Wert',
}: {
  data: Point[]
  color?: string
  unit?: string
  height?: number
  name?: string
}) {
  if (data.length === 0) return <ChartEmpty />
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={false} minTickGap={18} />
          <YAxis
            tick={AXIS}
            tickLine={false}
            axisLine={false}
            width={42}
            domain={['auto', 'auto']}
            tickFormatter={compact}
          />
          <Tooltip {...TOOLTIP_STYLE} formatter={(v) => [`${Math.round(Number(v) * 10) / 10} ${unit}`, name]} />
          <Line type="monotone" dataKey="value" stroke={color} strokeWidth={2.4} dot={{ r: 2.5, fill: color }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export function VolumeBarChart({
  data,
  unit = '',
  height = 190,
  color = '#3b82f6',
  highlightLast = true,
}: {
  data: Point[]
  unit?: string
  height?: number
  color?: string
  highlightLast?: boolean
}) {
  if (data.length === 0) return <ChartEmpty />
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={false} minTickGap={10} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} width={42} tickFormatter={compact} />
          <Tooltip
            {...TOOLTIP_STYLE}
            cursor={{ fill: '#ffffff10' }}
            formatter={(v) => [`${Math.round(Number(v))} ${unit}`, 'Volumen']}
          />
          <Bar dataKey="value" radius={[5, 5, 0, 0]}>
            {data.map((_, i) => (
              <Cell
                key={i}
                fill={highlightLast && i === data.length - 1 ? '#f5f5f7' : color}
                fillOpacity={highlightLast && i === data.length - 1 ? 1 : 0.75}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export interface DistributionSlice {
  label: string
  value: number
  color: string
}

/** Horizontale Balken — auf dem iPhone besser lesbar als ein Tortendiagramm. */
export function DistributionBars({ data }: { data: DistributionSlice[] }) {
  const total = data.reduce((a, d) => a + d.value, 0)
  if (total === 0) return <ChartEmpty />
  return (
    <div className="space-y-2.5">
      {data
        .filter((d) => d.value > 0)
        .sort((a, b) => b.value - a.value)
        .map((d) => (
          <div key={d.label} className="flex items-center gap-3">
            <div className="w-24 shrink-0 truncate text-sm">{d.label}</div>
            <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-ink-700">
              <div
                className="h-full rounded-full"
                style={{ width: `${(d.value / total) * 100}%`, background: d.color }}
              />
            </div>
            <div className="w-16 shrink-0 text-right text-xs text-mute tnum">
              {Math.round((d.value / total) * 100)}%
            </div>
          </div>
        ))}
    </div>
  )
}

function ChartEmpty() {
  return (
    <div className="flex h-32 items-center justify-center text-sm text-mute">
      Noch keine Daten für ein Diagramm.
    </div>
  )
}

export const MUSCLE_COLORS: Record<string, string> = {
  Brust: '#ef4444',
  Rücken: '#3b82f6',
  Schultern: '#f59e0b',
  Bizeps: '#8b5cf6',
  Trizeps: '#ec4899',
  Quadrizeps: '#22c55e',
  Hamstrings: '#14b8a6',
  Waden: '#06b6d4',
  Gesäß: '#f97316',
  Bauch: '#eab308',
  Unterarme: '#a1a1aa',
}
