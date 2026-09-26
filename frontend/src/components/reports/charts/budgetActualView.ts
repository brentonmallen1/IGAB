/** Pure presentation for Budget vs Actual: every figure is served. */
import { toCents } from '../../../utils/money'

/**
 * The headline card for the served `total_variance`: which way the window
 * went against its plans, then by how much.
 *
 * The card read "Variance" over a signed figure, and the figure was raw
 * `total_assigned - total_spent` — so it disagreed with the rows beneath it
 * wherever an envelope was drained, and a reader had to remember which sign
 * meant over. The figure is the rows' verdicts summed now, and the label says
 * the direction in words.
 */
export function varianceHeadline(
  totalVariance: number,
  formatMoney: (amount: number) => string
): { label: string; value: string; over: boolean } {
  const cents = toCents(totalVariance)
  if (cents === 0) return { label: 'Against plan', value: 'On plan', over: false }
  return cents < 0
    ? { label: 'Over plan by', value: formatMoney(-totalVariance), over: true }
    : { label: 'Under plan by', value: formatMoney(totalVariance), over: false }
}

/** What the % column says for a category with no plan to take a share of. */
export const NO_PLAN = 'no plan'
