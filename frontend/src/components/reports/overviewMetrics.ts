/** Pure metric math for the Overview dashboard cards. Extracted from
 * OverviewReport so the delta/rate math is unit-testable. */

/** Percent change vs the prior period, guarded for prev = 0 and using an
 * absolute denominator so a negative prior net worth doesn't flip the sign
 * of an improvement. */
export function netWorthDelta(current: number, prev: number): number {
  if (prev === 0) return 0
  return ((current - prev) / Math.abs(prev)) * 100
}

/** Percent change in spending vs the prior period; 0 when there was no
 * prior spending to compare against. */
export function spendingDelta(current: number, prev: number): number {
  if (prev <= 0) return 0
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
