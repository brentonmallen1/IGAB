/** Pure presentation for Spending Anomalies: every figure is served. */
import type { AnomalyItem, AnomalyReport } from '../../../types'

/** The anomalies grouped by month, NEWEST month first, each group worst first
 *  (the served order). Groups came in the order their worst row happened to
 *  rank, so a three-month-old spike could head the page above this month's. */
export function groupByMonthNewestFirst(
  anomalies: AnomalyItem[]
): { month: string; items: AnomalyItem[] }[] {
  const groups = new Map<string, AnomalyItem[]>()
  for (const a of anomalies) {
    const items = groups.get(a.month)
    if (items) items.push(a)
    else groups.set(a.month, [a])
  }
  return [...groups.entries()]
    .sort(([a], [b]) => (a < b ? 1 : a > b ? -1 : 0))
    .map(([month, items]) => ({ month, items }))
}

/** "+200%" against the baseline's mean; "+∞%" when the baseline is zero. */
export function percentChange(actual: number, baseline: number): string {
  if (baseline === 0) return actual > 0 ? '+∞%' : '0%'
  const pct = ((actual - baseline) / baseline) * 100
  return `${pct >= 0 ? '+' : ''}${Math.round(pct)}%`
}

/** What an empty report owes its reader: how much was actually tested. "No
 *  unusual spending" over a budget whose categories were all too young to
 *  score reads as a clean bill of health it never gave. */
export function testedLine(
  report: Pick<AnomalyReport, 'categories_seen' | 'categories_tested' | 'sinking_funds_skipped'>
): string {
  const { categories_seen: seen, categories_tested: tested } = report
  const noun = seen === 1 ? 'category' : 'categories'
  const base =
    seen === 0
      ? 'No spending to test yet.'
      : `${tested} of ${seen} ${noun} had six earlier months to test against.`
  const skipped = report.sinking_funds_skipped
  if (skipped === 0) return base
  const funds = skipped === 1 ? '1 sinking fund is' : `${skipped} sinking funds are`
  return `${base} ${funds} not tested: paying the bill a sinking fund saved for is the plan working.`
}
