import type { Transaction } from '../../../types'

/**
 * Which rows the review section holds onto.
 *
 * Note what is *not* here: the rule for whether a row needs a category. That
 * lives in exactly one place — `NEEDS_CATEGORY` in
 * `backend/src/igab/repositories/txn_filters.py` — and arrives on the row as
 * `needs_category`. This file used to re-derive it, and the copies drifted
 * twice: the register drew ~930 rows as unfiled under a badge that said 3,
 * because only the server had learned that a transfer leg whose partner never
 * imported is still a transfer. Read the field; never rebuild the rule.
 *
 * What *is* here is presentation: pending rows have their own section above
 * this one, and a row categorized mid-review is held in place so it doesn't
 * vanish the instant the category lands, sending the user hunting for it to
 * add a memo. A row that arrives unapproved is held until it's approved —
 * approving is the deliberate "I'm done with this one" action.
 */

/** Pending rows are provisional and render in their own section — never here.
 *  Mirrors the backend's POSTED, which every count applies alongside
 *  NEEDS_CATEGORY for the same reason. */
const isPending = (t: Transaction) => t.cleared === 'pending'

/**
 * Returns `prev` unchanged when nothing moved, so callers can use it as React
 * state without re-rendering on every refetch.
 */
export function nextHeldForReview(
  prev: ReadonlySet<string>,
  transactions: Transaction[]
): ReadonlySet<string> {
  const next = new Set(prev)
  let changed = false
  for (const t of transactions) {
    if (!isPending(t) && t.needs_category && !t.approved && !next.has(t.id)) {
      next.add(t.id)
      changed = true
    } else if (next.has(t.id) && t.approved) {
      next.delete(t.id)
      changed = true
    }
  }
  return changed ? next : prev
}

export function inReviewSection(t: Transaction, heldIds: ReadonlySet<string>): boolean {
  if (isPending(t)) return false
  return t.needs_category || (!t.approved && heldIds.has(t.id))
}
