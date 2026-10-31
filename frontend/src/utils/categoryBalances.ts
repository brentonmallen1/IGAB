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

/**
 * A served month with some envelopes' Assigned set — the optimistic picture
 * shown while the server writes them. One implementation for every write
 * that sets figures: typing in a cell (one envelope) and the inspector's
 * Auto-Assign buttons (many). Available moves one for one with Assigned, and
 * Ready to Assign and the month's total by the sum of the changes; the
 * refetch that follows replaces all of it with the server's figures,
 * including the ripple into other months this does not attempt.
 *
 * An envelope with no row yet gets one at the new figure with nothing else
 * claimed: the target verdict and the card split are the server's to say.
 */
export function withAssignments(
  month: BudgetMonth,
  monthKey: string,
  amounts: ReadonlyMap<string, number>
): BudgetMonth {
  const existing = balancesByCategory(month)
  let total = 0
  const category_balances = month.category_balances.map((b) => {
    const amount = amounts.get(b.category_id)
    if (amount === undefined) return b
    const delta = amount - Number(b.assigned ?? 0)
    total += delta
    return { ...b, assigned: amount, available: Number(b.available ?? 0) + delta }
  })
  for (const [categoryId, amount] of amounts) {
    if (existing.has(categoryId)) continue
    total += amount
    category_balances.push({
      category_id: categoryId,
      month: monthKey,
      assigned: amount,
      activity: 0,
      available: amount,
      // The server owns the target verdict and has not answered yet. null
      // hides the pill for one refetch rather than inventing a status here,
      // which is the rule this field exists to enforce.
      target_status: null,
      // A row invented optimistically is never a card's envelope — those
      // always exist server-side before they can be assigned.
      is_card_payment: false,
      needed_this_month: null,
      target_assigned: null,
      // Nothing repaid: this row is an assignment just made, not a card
      // inflow the exposure walk had to split.
      repaid_uncovered_debt: 0,
      // A row that starts at `assigned` with no activity cannot be
      // overspent, let alone on a card. The refetch brings the real split.
      credit_overspent: 0,
    })
  }
  return {
    ...month,
    total_assigned: Number(month.total_assigned) + total,
    to_be_assigned: Number(month.to_be_assigned) - total,
    category_balances,
  }
}
