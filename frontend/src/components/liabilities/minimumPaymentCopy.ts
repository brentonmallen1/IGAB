/**
 * Saying a minimum-payment rule in words, once.
 *
 * Two surfaces need it — the terms tile's subtitle and the payoff copy — and
 * a phrase written twice is a phrase that ends up disagreeing about whether
 * the floor is a minimum or a maximum.
 *
 * Pure presentational composition of server-supplied facts, so it lives here
 * rather than on the server: the server decides the *number*
 * (`minimum_payment_due_now`, which it computes from the balance and the
 * interest it owns), and this only decides how to say what kind of rule
 * produced it.
 */

import type { Liability } from '../../api/liabilities'

type RuleFields = Pick<
  Liability,
  | 'minimum_payment_kind'
  | 'minimum_payment_percent'
  | 'minimum_payment_floor'
  | 'minimum_payment_plus_interest'
>

/**
 * "2% of balance, at least $35" — or null for a fixed amount, where the
 * figure on screen already says everything there is to say.
 */
export function describeMinimumRule(
  liability: RuleFields,
  formatMoney: (n: number) => string
): string | null {
  if (liability.minimum_payment_kind !== 'percent_of_balance') return null
  const percent = liability.minimum_payment_percent
  const floor = liability.minimum_payment_floor
  if (percent === null) return null

  const plus = liability.minimum_payment_plus_interest ? ' plus interest' : ''
  const atLeast = floor === null ? '' : `, at least ${formatMoney(floor)}`
  return `${percent}% of balance${plus}${atLeast}`
}

/**
 * Whether the figure shown will fall as the balance does.
 *
 * The payoff copy quotes a monthly amount ("The $182 minimum doesn't cover
 * this month's ~$190 interest"). With a percentage rule that number is
 * this month's, and saying so is the difference between a fact and a
 * projection someone will later find was wrong.
 */
export function minimumDeclines(liability: RuleFields): boolean {
  return (
    liability.minimum_payment_kind === 'percent_of_balance' &&
    liability.minimum_payment_percent !== null
  )
}
