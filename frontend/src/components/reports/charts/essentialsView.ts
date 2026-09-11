/** Pure view math for the Essentials report, extracted so it is testable
 * without mounting a chart. */
import { fromCents, sumToCents } from '../../../utils/money'
import { shareOfTotal } from '../drillDownTotals'

interface MonthTotal {
  month: string
  total: number
}

/**
 * A category's share of what a lean month costs, as a display percentage.
 *
 * Share of `monthly_total_average` — the table's own footer figure — NOT of
 * the largest category. The old bar scaled to the max, which only restated
 * "this is the biggest number" beside the number itself; "Rent is 54% of a
 * lean month" is a fact the table did not carry. Can exceed 100 only if the
 * inputs disagree, so the caller clamps the drawn width, not the figure.
 */
export function shareOfLeanMonth(monthlyAverage: number, monthlyTotalAverage: number): number {
  // A bar needs a width, so "no share to state" draws as no bar at all.
  return shareOfTotal(monthlyAverage, monthlyTotalAverage) ?? 0
}

/**
 * The most expensive month in the window — the stress case a reserve built
 * on the 90-day headline has to survive. Null when no month saw spending:
 * "the worst month cost $0" is not a claim worth a card.
 */
export function worstMonth(series: MonthTotal[]): MonthTotal | null {
  let worst: MonthTotal | null = null
  for (const m of series) {
    if (m.total > 0 && (worst === null || m.total > worst.total)) worst = m
  }
  return worst
}

/**
 * The footer under the table's Total column: the column's own sum, in cents.
 *
 * Not the rounded monthly average times the month count — those differ by up
 * to a penny per category per month, and a footer that does not add up to
 * the column above it is the one number on the table a reader can check.
 */
export function columnTotal(rows: readonly { total: number }[]): number {
  return fromCents(sumToCents(rows.map((r) => r.total)))
}
