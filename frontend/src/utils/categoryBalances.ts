import type { BudgetMonth, CategoryBalance } from '../types'

/**
 * A served month's balances, keyed by category id.
 *
 * One spelling of the lookup. The budget grid built this map with a
 * `forEach`, the multi-month sheet with `new Map(...map)`, the cards strip
 * twice more for single fields, and the optimistic assignment a linear
 * `find` — five hand-written copies of "which balance is this category's".
 * A month that has not loaded is an empty map, never a map of zeros.
 */
export function balancesByCategory(
  month: Pick<BudgetMonth, 'category_balances'> | null | undefined
): Map<string, CategoryBalance> {
  return new Map((month?.category_balances ?? []).map((b) => [b.category_id, b]))
}

/** How an envelope's Available reads: the grid's colour classes. */
export type AvailableTone = 'positive' | 'zero' | 'negative' | 'negative-on-card'

/**
 * The tone of a served Available.
 *
 * Red that was swiped on a card (`credit_overspent` covers all of it) is
 * still negative, but it never charges Ready to Assign and rides onto the
 * card at the month boundary — so it reads calmly, not as the alarm colour.
 * Both figures are the server's (domain/cards.py); this only names the
 * reading. It lived inline in CategoryRow; the quick-add toast is its second
 * reader, and a toast that turned red where the grid stays calm would be the
 * app contradicting itself.
 */
export function availableTone(
  balance: Pick<CategoryBalance, 'available' | 'credit_overspent'>
): AvailableTone {
  const available = Number(balance.available ?? 0)
  const creditOverspent = Number(balance.credit_overspent ?? 0)
  if (available < 0) return creditOverspent >= -available ? 'negative-on-card' : 'negative'
  return available > 0 ? 'positive' : 'zero'
}
