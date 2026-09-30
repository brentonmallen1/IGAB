import type { SplitCheck } from '../../../utils/splits'

/**
 * What a split says about itself on a phone — the summary row in the form
 * and the status at the top of the split sheet. Pure presentation of
 * `checkSplit`'s answer (utils/splits), so the two cannot describe one split
 * two ways.
 */

export type SplitTone = 'done' | 'short' | 'over' | 'incomplete'

export interface SplitStatus {
  tone: SplitTone
  text: string
}

/** Money first: while the lines don't add up that is the thing to fix, and
 *  a missing category or amount only matters once they do. */
export function splitStatus(check: SplitCheck, formatMoney: (n: number) => string): SplitStatus {
  if (check.reason === 'no-total') return { tone: 'incomplete', text: 'Enter the total first' }
  if (check.remainingCents > 0)
    return { tone: 'short', text: `${formatMoney(check.remainingCents / 100)} left` }
  if (check.remainingCents < 0)
    return { tone: 'over', text: `${formatMoney(-check.remainingCents / 100)} over` }
  if (check.reason === 'missing-category')
    return { tone: 'incomplete', text: 'Every line needs a category' }
  if (check.reason === 'non-positive-leg')
    return { tone: 'incomplete', text: 'Every line needs an amount' }
  return { tone: 'done', text: 'Fully split' }
}

/** How much of the total the lines cover, 0–100, for the progress bar. */
export function splitProgress(check: SplitCheck): number {
  if (check.totalCents <= 0) return 0
  return Math.max(0, Math.min(100, (check.assignedCents / check.totalCents) * 100))
}

/** The categories in the split, as one short line: "Groceries, Household, +2". */
export function splitLabel(
  legs: readonly { categoryId: string | null }[],
  nameOf: (id: string) => string
): string {
  const names = [
    ...new Set(legs.flatMap((l) => (l.categoryId ? [nameOf(l.categoryId)] : []))),
  ].filter(Boolean)
  if (names.length === 0) return `${legs.length} lines, no categories yet`
  if (names.length <= 2) return names.join(', ')
  return `${names[0]}, ${names[1]}, +${names.length - 2}`
}
