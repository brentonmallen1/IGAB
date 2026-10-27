import type { PendingReviewCounts } from '../../api/transactions'

/**
 * What the review banner says, and the search its View button runs.
 *
 * Shared by the banner (desktop, and the budget-wide one) and the phone's
 * "Needs a look" sheet, which lists the same rows under the same words — a
 * sheet that counted or phrased them its own way would be free to disagree
 * with the banner one breakpoint over.
 */

/** The rows the banner counts: waiting on a look, and posted. Pending holds
 *  wait to post before they ask anything (txn_filters.NEEDS_APPROVAL). */
export const REVIEW_SEARCH = 'is: unapproved OR is: uncategorized NOT is: pending'

/** "15 transactions to review" — no closing stop; the banner adds its own. */
export function reviewPhrase(total: number): string {
  return total === 1 ? '1 transaction to review' : `${total} transactions to review`
}

/** "13 to approve · 3 to categorize", in the account dot's words
 *  (utils/accountAttention). A row that is both appears in both. */
export function reviewBreakdown(counts: PendingReviewCounts): string {
  const parts = [
    counts.unapproved > 0 ? `${counts.unapproved} to approve` : null,
    counts.uncategorized > 0 ? `${counts.uncategorized} to categorize` : null,
  ]
  return parts.filter(Boolean).join(' · ')
}
