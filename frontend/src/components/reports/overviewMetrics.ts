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

/** Savings rate as a display percentage, clamped at 0 (an overspent period
 * reads as 0%, not a negative rate). */
export function clampedSavingsRate(rate: number | null | undefined): number | null {
  // null passes through: the server says null when no income was recorded, and
  // showing 0% there claims the household saved nothing rather than that there
  // was nothing to save from.
  return rate == null ? null : Math.max(0, rate * 100)
}

/** Whole-day display value; null passes through (no runway to show). */
export function roundedDaysUntilZero(days: number | string | null | undefined): number | null {
  return days != null ? Math.round(Number(days)) : null
}
