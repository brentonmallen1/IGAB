/** Pure metric math for the Overview dashboard cards. Extracted from
 * OverviewReport so the delta/rate math is unit-testable. */

/** Percent change vs the prior period, guarded for prev = 0 and using an
 * absolute denominator so a negative prior net worth doesn't flip the sign
 * of an improvement. */
export function netWorthDelta(current: number, prev: number): number {
  if (prev === 0) return 0
  return ((current - prev) / Math.abs(prev)) * 100
}

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

/** Whole-day display value; null passes through (no runway to show). */
export function roundedDaysUntilZero(days: number | string | null | undefined): number | null {
  return days != null ? Math.round(Number(days)) : null
}

/** N months of essentials as a save target; null passes through (nothing is
 *  tagged Essential yet, so there is no figure to multiply). */
export function essentialsReserve(
  monthly: number | null | undefined,
  months: number
): number | null {
  return monthly == null ? null : monthly * months
}
