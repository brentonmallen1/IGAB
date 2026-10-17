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
 * date. A funding target with a stop fills the same way, toward its stop:
 * "$100 a month, stop at $1,000" is a balance being built at a pace, like a
 * dated goal. Other funding targets fill by ASSIGNED — "how much of this
 * month's duty is done".
 */
export function targetProgress(
  target: Pick<CategoryTarget, 'target_type' | 'target_amount' | 'target_limit'>,
  assigned: number,
  available: number
): number | null {
  if (target.target_limit != null) {
    if (target.target_limit <= 0) return null
    return Math.min(Math.max(available / target.target_limit, 0), 1)
  }
  const amount = target.target_amount
  if (amount <= 0) return null
  const numerator = target.target_type === 'savings_balance' ? available : assigned
  return Math.min(Math.max(numerator / amount, 0), 1)
}

/**
 * What a target asks for, in words: "$100/mo, stops at $1,000", "$25/wk",
 * "$1,000". Presentation of the stored fields only — what the month asks for
 * once the stop is near is the server's (`needed_this_month`).
 */
export function describeTarget(
  target: Pick<CategoryTarget, 'target_type' | 'target_amount' | 'target_limit'>,
  formatMoney: (amount: number) => string
): string {
  const per =
    target.target_type === 'monthly_funding'
      ? '/mo'
      : target.target_type === 'weekly_funding'
        ? '/wk'
        : ''
  const rate = `${formatMoney(target.target_amount)}${per}`
  return target.target_limit != null
    ? `${rate}, stops at ${formatMoney(target.target_limit)}`
    : rate
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
