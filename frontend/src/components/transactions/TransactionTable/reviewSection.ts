import type { Payee, Transaction } from '../../../types'

/** Payee id → the account that payee transfers to. Built once per render and
 *  threaded through, mirroring how `onBudgetAccountIds` is passed. */
export function transferTargets(payees: Payee[]): ReadonlyMap<string, string> {
  const map = new Map<string, string>()
  for (const p of payees) {
    if (p.transfer_account_id) map.set(p.id, p.transfer_account_id)
  }
  return map
}

/**
 * Rows genuinely missing a category. Off-budget accounts don't use categories,
 * so their rows never qualify.
 *
 * This mirrors the backend's `NEEDS_CATEGORY` (repositories/txn_filters.py) and
 * has to stay in step with it: the two answer the same question, one for a
 * badge count and one for the section a row is drawn in, and a user who presses
 * a count of 3 and finds 930 rows has been lied to by whichever drifted.
 *
 * It used to test `!t.transfer_id`, which recognises only a transfer whose
 * partner also imported. A YNAB export routinely writes legs whose partner
 * never arrives — the account was skipped, or the pair never matched — and
 * every one of those was drawn as unfiled. A transfer payee is the other half
 * of the signal, and the backend has read both for a while.
 */
export function needsCategory(
  t: Transaction,
  onBudgetAccountIds: ReadonlySet<string>,
  transferTargetByPayee: ReadonlyMap<string, string> = new Map()
): boolean {
  if (t.cleared === 'pending' || t.category_id || t.is_split) return false
  if (!onBudgetAccountIds.has(t.account_id)) return false

  const target = t.payee_id ? transferTargetByPayee.get(t.payee_id) : undefined
  if (!t.transfer_id && target === undefined) return true // not a transfer at all

  // It is a transfer. One still needs a category: money leaving the budget.
  // A mortgage payment is a transfer to an off-budget account, and budgeting
  // for it is the point. An unresolvable counterpart reads as on-budget, the
  // same coalesce the backend's COUNTERPART_OFF_BUDGET makes.
  return target !== undefined && !onBudgetAccountIds.has(target)
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
  onBudgetAccountIds: ReadonlySet<string>,
  transferTargetByPayee: ReadonlyMap<string, string> = new Map()
): ReadonlySet<string> {
  const next = new Set(prev)
  let changed = false
  for (const t of transactions) {
    if (
      needsCategory(t, onBudgetAccountIds, transferTargetByPayee) &&
      !t.approved &&
      !next.has(t.id)
    ) {
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
  heldIds: ReadonlySet<string>,
  transferTargetByPayee: ReadonlyMap<string, string> = new Map()
): boolean {
  return (
    needsCategory(t, onBudgetAccountIds, transferTargetByPayee) ||
    (t.cleared !== 'pending' && !t.approved && heldIds.has(t.id))
  )
}
