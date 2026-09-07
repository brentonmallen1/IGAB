/** The funding day a person may pick, 1–31 — matching MAX_FUNDING_DAY in
 *  backend/src/igab/domain/targets.py, which clamps it to each month's real
 *  length so "the 31st" means the last day in a month that has none. */
export const MAX_FUNDING_DAY = 31

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
 * The verdict and the amount arrive on the row as `target_status` and
 * `needed_this_month` (see `CategoryBalance`). What is left here is how far to
 * fill a bar, which the server never decides and never needs to.
 */
import type { CategoryTarget } from '../types'

/**
 * Progress toward the target's own measure, 0..1.
 *
 * A savings balance — dated or not — fills by AVAILABLE: the bar answers "how
 * much of the goal balance exists", which is the picture a person saving
 * toward a figure wants even when the server paces this month's ask by the
 * date. Funding targets fill by ASSIGNED — "how much of this month's duty is
 * done".
 */
export function targetProgress(
  target: Pick<CategoryTarget, 'target_type' | 'target_amount'>,
  assigned: number,
  available: number
): number | null {
  const amount = target.target_amount
  if (amount <= 0) return null
  const numerator = target.target_type === 'savings_balance' ? available : assigned
  return Math.min(Math.max(numerator / amount, 0), 1)
}

/** Whether the server judges this target on the balance rather than on this
 *  month's assignment — an undated savings balance, and nothing else. Mirrors
 *  `TargetService.measures_balance` for WORDING only ("Save $X more" against
 *  "Need $X this month"); never used to decide an amount. */
export function targetMeasuresBalance(
  target: Pick<CategoryTarget, 'target_type' | 'target_date'>
): boolean {
  return target.target_type === 'savings_balance' && !target.target_date
}
