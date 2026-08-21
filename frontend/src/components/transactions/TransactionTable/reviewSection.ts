import type { Transaction } from '../../../types'

/**
 * Rows genuinely missing a category. Off-budget accounts don't use
 * categories, so their rows never qualify.
 */
export function needsCategory(t: Transaction, onBudgetAccountIds: ReadonlySet<string>): boolean {
  return (
    t.cleared !== 'pending' &&
    !t.category_id &&
    !t.transfer_id &&
    !t.is_split &&
    onBudgetAccountIds.has(t.account_id)
  )
}

/**
 * Which rows the review section holds onto.
 *
 * Assigning a category would otherwise drop a row out of the section the
 * instant the category lands, sending the user hunting for it again to add a
 * memo. A row that arrives here unapproved is held until it's approved —
 * approving is the deliberate "I'm done with this one" action.
 *
 * Returns `prev` unchanged when nothing moved, so callers can use it as
 * React state without re-rendering on every refetch.
 */
export function nextHeldForReview(
  prev: ReadonlySet<string>,
  transactions: Transaction[],
  onBudgetAccountIds: ReadonlySet<string>
): ReadonlySet<string> {
  const next = new Set(prev)
  let changed = false
  for (const t of transactions) {
    if (needsCategory(t, onBudgetAccountIds) && !t.approved && !next.has(t.id)) {
      next.add(t.id)
      changed = true
    } else if (next.has(t.id) && t.approved) {
      next.delete(t.id)
      changed = true
    }
  }
  return changed ? next : prev
}

export function inReviewSection(
  t: Transaction,
  onBudgetAccountIds: ReadonlySet<string>,
  heldIds: ReadonlySet<string>
): boolean {
  return (
    needsCategory(t, onBudgetAccountIds) ||
    (t.cleared !== 'pending' && !t.approved && heldIds.has(t.id))
  )
}
