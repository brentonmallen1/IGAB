/** Pure metric math for the Overview dashboard cards. Extracted from
 * OverviewReport so the delta/rate math is unit-testable. */
import type { OverviewRunway } from '../../types'

/** Percent change in spending vs the prior period; null when there was no
 * prior spending to compare against — not 0, which would read "unchanged".
 *
 * Every spending comparison reads this for whether a percentage exists at
 * all: the Spent card's delta, the means dialog's sentence and both burn-rate
 * lines (`charts/burnRateView.ts`). The first two each guarded `prev > 0`
 * beside a function that returned 0 for the same case, so the rule was
 * written three times. */
export function spendingDelta(current: number, prev: number): number | null {
  if (prev <= 0) return null
  return ((current - prev) / prev) * 100
}

/**
 * Why the Overview's Runway read something other than its default (Essentials
 * against checking and the emergency fund), or null when it did not fall back.
 * The server picks the fallback (`domain/runway.default_basis`) and serves
 * why; this only says it.
 */
export function runwayFallback(
  runway: Pick<OverviewRunway, 'fund_chosen' | 'essentials_known'>
): string | null {
  const reasons = [
    ...(runway.essentials_known ? [] : ['nothing tagged Essential']),
    ...(runway.fund_chosen ? [] : ['no emergency fund chosen']),
  ]
  if (reasons.length === 0) return null
  const said = reasons.join(', ')
  return said[0].toUpperCase() + said.slice(1)
}

/**
 * The heading over the Overview's "this period" cards: which days they read,
 * and "so far" when the range runs to today — a month in progress is half a
 * month, and its income and spending are month-to-date.
 *
 * A whole calendar month reads as the month ("Aug 26"); the running month
 * from its 1st reads "Sep 26 so far"; anything else is its first and last day
 * ("Jul 3 – Aug 12"), "so far" appended when it reaches today. Takes the
 * page's formatters, so the date-format setting holds.
 */
export function periodHeading(
  start: string,
  end: string,
  today: string,
  formatMonthShort: (month: string) => string,
  formatDayMonth: (day: string) => string
): string {
  const running = end >= today
  const sameMonth = start.slice(0, 7) === end.slice(0, 7)
  const fromFirst = start.endsWith('-01')
  const monthEnd = end === lastDayOf(end)
  if (sameMonth && fromFirst && (running || monthEnd)) {
    const label = formatMonthShort(start)
    return running ? `${label} so far` : label
  }
  const range = `${formatDayMonth(start)} – ${formatDayMonth(end)}`
  return running ? `${range}, so far` : range
}

/** The last day of `day`'s month, whatever today is. */
function lastDayOf(day: string): string {
  const [y, m] = day.split('-').map(Number)
  return `${y}-${String(m).padStart(2, '0')}-${String(new Date(y, m, 0).getDate()).padStart(2, '0')}`
}
