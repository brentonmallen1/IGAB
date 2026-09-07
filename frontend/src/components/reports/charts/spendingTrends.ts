/**
 * Pure rollup for the Spending Trends report: the server serves one series
 * per category; the chart can show them per group instead. Presentation
 * only — every figure is the server's, summed.
 */
import type { SpendingTrendsReport } from '../../../types'

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
