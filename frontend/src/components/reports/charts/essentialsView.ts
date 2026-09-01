/** Pure view math for the Essentials report, extracted so it is testable
 * without mounting a chart. */

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
  if (monthlyTotalAverage <= 0) return 0
  return (monthlyAverage / monthlyTotalAverage) * 100
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
