/**
 * Pure rollup for the Spending Trends report: the server serves one series
 * per category; the chart can show them per group instead. Presentation
 * only — every figure is the server's, summed.
 */
import type { SpendingTrendsReport } from '../../../types'
import { otherBand } from '../drillDownTotals'
import { chartColor, COLOR_OTHER } from './chartColors'

export interface TrendRow {
  key: string
  name: string
  group_name: string | null
  monthly: number[]
  total: number
}

export function rollupTrends(
  data: SpendingTrendsReport,
  groupBy: 'group' | 'category' | 'payee'
): TrendRow[] {
  if (groupBy !== 'group') {
    return data.series.map((s) => ({
      key: s.id,
      name: s.name,
      group_name: s.group_name,
      monthly: s.monthly,
      total: s.total,
    }))
  }
  const byGroup = new Map<string, TrendRow>()
  for (const s of data.series) {
    const key = s.group_id ?? '__none__'
    const row = byGroup.get(key) ?? {
      key,
      name: s.group_name ?? 'Ungrouped',
      group_name: null,
      monthly: data.months.map(() => 0),
      total: 0,
    }
    s.monthly.forEach((v, i) => {
      row.monthly[i] = (row.monthly[i] ?? 0) + v
    })
    row.total += s.total
    byGroup.set(key, row)
  }
  return [...byGroup.values()].sort((a, b) => b.total - a.total)
}

/** How many series the chart draws on their own before the rest is Other. */
export const MAX_TREND_SERIES = 10

/** The chart-row key the Other band is stored under. Series are keyed by id,
 *  never by name, so a category called "Other" is not the band. */
export const OTHER_KEY = '__other__'

export interface TrendSeries {
  /** The chart-row key: a category or group id, or `OTHER_KEY`. */
  key: string
  name: string
  color: string
  /** The series' total over the window, for the legend. */
  total: number
}

export interface StackedTrends {
  /** One row per month: its axis label under `month`, each drawn series'
   *  figure under its key. */
  rows: Record<string, string | number>[]
  /** The drawn series in stack order, bottom first — Other last, and only
   *  when some month has something outside the named series. */
  series: TrendSeries[]
}

/**
 * The stacked chart's rows and series: the largest `maxSeries` by name, and
 * one Other band holding the rest, so every bar is the month the axis, the
 * cards and the table's All row report.
 *
 * The chart stacked only the ten largest series and nothing else, so each
 * bar stood at 56–84% of its month under an axis that read as totals, and the
 * tooltip needed a separate "All categories" line to say what the bar left
 * out. Other is the remainder by `otherBand` — Income by Source's rule — and
 * can be negative in a month the tail refunded more than it spent.
 */
export function stackTrends(
  data: Pick<SpendingTrendsReport, 'months' | 'monthly_totals'>,
  rolled: readonly TrendRow[],
  formatMonth: (month: string) => string,
  maxSeries: number = MAX_TREND_SERIES
): StackedTrends {
  const shown = rolled.slice(0, maxSeries)
  const rest = data.months.map((_, i) =>
    otherBand(
      data.monthly_totals[i] ?? 0,
      shown.map((s) => s.monthly[i] ?? 0)
    )
  )
  const rows = data.months.map((m, i) => {
    const row: Record<string, string | number> = { month: formatMonth(m) }
    for (const s of shown) row[s.key] = s.monthly[i] ?? 0
    const other = rest[i]
    if (other !== null) row[OTHER_KEY] = other
    return row
  })
  const series: TrendSeries[] = shown.map((s, i) => ({
    key: s.key,
    name: s.name,
    color: chartColor(i),
    total: s.total,
  }))
  if (rest.some((r) => r !== null)) {
    series.push({
      key: OTHER_KEY,
      name: 'Other',
      color: COLOR_OTHER,
      total: rest.reduce<number>((sum, r) => sum + (r ?? 0), 0),
    })
  }
  return { rows, series }
}
