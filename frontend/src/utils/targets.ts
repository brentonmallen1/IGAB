/**
 * Target *presentation* — bar geometry, and nothing that decides money.
 *
 * This module used to mirror the backend's `TargetService.calculate_status`,
 * with a docblock instructing the next reader to change both copies together.
 * They drifted anyway, in three separate ways: the monthly-pace division was
 * applied to the wrong target type, the month clamp differed, and
 * `CategoryRow` grew a third implementation of the shortfall that contradicted
 * both. A pill that predicts what Fill Underfunded will do cannot be computed
 * from a second guess at the rule.
 *
 * The verdict and the amount now arrive on the row as `target_status` and
 * `needed_this_month` (see `CategoryBalance`). What is left here is how far to
 * fill a bar, which the server never decides and never needs to.
 */
import type { CategoryTarget } from '../types'

/**
 * Progress toward the target's own measure, 0..1.
 *
 * Balance-shaped targets (savings balance, dated needed-for-spending) fill by
 * AVAILABLE — the bar answers "how much of the goal balance exists". Funding
 * targets fill by ASSIGNED — "how much of this month's duty is done".
 */
export function targetProgress(
  target: Pick<CategoryTarget, 'target_type' | 'target_amount' | 'target_date'>,
  assigned: number,
  available: number
): number | null {
  const amount = Number(target.target_amount)
  if (amount <= 0) return null
  const numerator = targetMeasuresBalance(target) ? available : assigned
  return Math.min(Math.max(numerator / amount, 0), 1)
}

/** Whether the target is a balance goal (the bar fills by AVAILABLE).
 *  Mirrors `TargetService.measures_balance`, and is only ever used to pick
 *  which number fills a bar — never to decide an amount. */
export function targetMeasuresBalance(
  target: Pick<CategoryTarget, 'target_type' | 'target_date'>
): boolean {
  return (
    target.target_type === 'savings_balance' ||
    (target.target_type === 'needed_for_spending' && !!target.target_date)
  )
}

/**
 * Whole months from now until `isoDate`, floored at 1 — for the "$X/mo to
 * goal" hint only.
 *
 * Presentational pacing, not a funding rule: it divides a shortfall the server
 * computed to suggest a rate. Browser-local months can differ from the
 * server's by one at a month boundary, which shifts the suggested rate
 * slightly and contradicts no verdict.
 */
export function monthsUntil(isoDate: string, now: Date = new Date()): number {
  const end = new Date(isoDate + 'T00:00:00')
  return Math.max(1, (end.getFullYear() - now.getFullYear()) * 12 + (end.getMonth() - now.getMonth()))
}
