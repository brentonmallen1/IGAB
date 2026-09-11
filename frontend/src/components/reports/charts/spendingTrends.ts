/**
 * Pure rollup for the Spending Trends report: the server serves one series
 * per category; the chart can show them per group instead. Presentation
 * only — every figure is the server's, summed.
 */
import type { SpendingTrendsReport } from '../../../types'
import type { WiderSet } from '../drillDownTotals'

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

/** The whole month behind a stacked tooltip, looked up by the axis label
 * recharts hands the tooltip.
 *
 * Only the largest series are stacked, so the tooltip's own sum is a
 * subtotal; this is what the table's All row draws for that month. A label
 * it does not know gets no wider figure. The lookup's `?? 0` printed
 * "All categories $0.00" on a miss, which is a month of no spending. */
export function monthWiderByLabel(
  data: Pick<SpendingTrendsReport, 'months' | 'monthly_totals'>,
  formatMonth: (month: string) => string
): (label: string) => WiderSet | undefined {
  const byLabel = new Map(data.months.map((m, i) => [formatMonth(m), data.monthly_totals[i]]))
  return (label) => {
    const total = byLabel.get(label)
    return total === undefined ? undefined : { total, label: 'categories' }
  }
}
