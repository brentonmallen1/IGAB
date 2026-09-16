import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceArea,
  ReferenceLine,
  Rectangle,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type BarShapeProps,
} from 'recharts'
import { ChartTooltip } from './charts/ChartTooltip'
import {
  AT_MEANS_BAND_PCT,
  MEANS_TREND_CLAMP_PCT,
  drawnMargin,
  marginPhrase,
  type MeansStanding,
  type MeansTrend,
  type MeansTrendBar,
} from './livingMeans'
import './MeansStanding.css'
import './MeansTrendChart.css'

/**
 * The Means trend's bars: each month's margin, signed so that up is kept, over
 * the ±`AT_MEANS_BAND_PCT` band the Your Means card reads by.
 *
 * **Presentational.** Everything drawn comes in as `meansTrend()`'s output, so
 * the Overview card (served months) and the Guide's example (invented months)
 * draw the same chart from the same function — neither re-draws it.
 *
 * `variant="strip"` is the card's miniature: bars and the zero line only, no
 * axes or tooltip, because it sits under the card's own button and says
 * nothing a reader can hover for. The caller names it with `label`.
 */
interface Props {
  trend: MeansTrend
  /** Month label for the axis and tooltip: the page's short month format. */
  formatMonth: (month: string) => string
  variant?: 'full' | 'strip'
  /** The chart's accessible name. Omit it where a table beside the chart
   *  already states every figure and the chart is decoration to a reader. */
  label?: string
  height?: number
}

interface Row {
  month: string
  /** Null for a month with no income: no bar, not a zero bar. */
  drawn: number | null
  standing: MeansStanding
  bar: MeansTrendBar
}

export function MeansTrendChart({ trend, formatMonth, variant = 'full', label, height }: Props) {
  const strip = variant === 'strip'
  const rows: Row[] = trend.bars.map((bar) => ({
    month: formatMonth(bar.month),
    drawn: bar.marginPct === null ? null : drawnMargin(bar.marginPct),
    standing: bar.reading.standing,
    bar,
  }))
  // Always tall enough to show the band, never taller than the clamp.
  const reach = Math.max(
    AT_MEANS_BAND_PCT * 2,
    ...rows.map((r) => (r.drawn === null ? 0 : Math.abs(r.drawn)))
  )
  const domain: [number, number] = [-reach, reach]

  return (
    <div
      className={`means-trend-chart means-trend-chart--${variant}`}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      <ResponsiveContainer width="100%" height={height ?? (strip ? 40 : 240)}>
        <BarChart
          data={rows}
          margin={
            strip
              ? { top: 2, right: 0, left: 0, bottom: 2 }
              : { top: 8, right: 8, left: 0, bottom: 0 }
          }
          barCategoryGap={strip ? '20%' : '25%'}
        >
          {!strip && (
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" vertical={false} />
          )}
          <XAxis dataKey="month" hide={strip} tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
          <YAxis
            hide={strip}
            domain={domain}
            allowDataOverflow
            tickFormatter={(v: number) => `${v}%`}
            tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
            width={48}
          />
          {/* The band as a range, as the Your Means dialog states it: inside
              it a month was at its means, whichever side of zero. */}
          <ReferenceArea
            y1={-AT_MEANS_BAND_PCT}
            y2={AT_MEANS_BAND_PCT}
            className="means-trend-chart__band"
            stroke="none"
            ifOverflow="hidden"
          />
          <ReferenceLine y={0} className="means-trend-chart__zero" />
          {!strip && (
            <Tooltip
              cursor={{ fill: 'var(--row-hover-bg)' }}
              isAnimationActive={false}
              content={(props) => <MeansTooltip {...props} />}
            />
          )}
          <Bar
            dataKey="drawn"
            isAnimationActive={false}
            shape={(props: BarShapeProps) => <StandingBar {...props} />}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/** A bar coloured by its month's standing — the colour is MeansStanding.css's,
 *  read through a class so no hue is written here. */
function StandingBar(props: BarShapeProps) {
  const row = props.payload as Row
  return (
    <Rectangle
      {...props}
      radius={2}
      className={`means-trend-chart__bar means-standing--${row.standing}`}
    />
  )
}

/** The real margin, never the clamped one the bar is drawn to. */
function MeansTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: readonly { payload?: unknown }[]
}) {
  const row = payload?.[0]?.payload as Row | undefined
  if (!active || !row) return null
  const { reading } = row.bar
  const clamped = row.bar.marginPct !== null && Math.abs(row.bar.marginPct) > MEANS_TREND_CLAMP_PCT
  return (
    <ChartTooltip
      active
      label={row.month}
      payload={[{ name: reading.margin ? reading.label : 'No income', value: 0 }]}
      formatter={() =>
        reading.margin ? `${marginPhrase(reading.margin)}${clamped ? ' (bar cut off)' : ''}` : '—'
      }
    />
  )
}
