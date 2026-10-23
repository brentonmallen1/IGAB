import type { Account } from '../types'

/**
 * How urgent an account's waiting rows look — one dot, coloured by the most
 * urgent thing on it.
 *
 * The sidebar used to draw a count of uncategorized rows and nothing else, so
 * an account full of rows to approve looked clear. A number was the wrong
 * shape anyway: on a row of names and balances it read as one more figure to
 * parse. The dot says "look here"; its label says what for.
 *
 * Which rows count is the server's (AccountRepository.attention_counts_for,
 * on the same predicates as the review banner). Ranking them into a colour is
 * presentation of those facts, which the server never decides, so it lives
 * here once for every surface that draws the dot.
 */

export type AttentionCounts = Pick<
  Account,
  'uncategorized_count' | 'unapproved_count' | 'pending_count'
>

/** Most urgent first. `categorize`: rows wait to be filed, so the budget is
 *  not yet right — the warning colour. `approve`: rows wait only for a look;
 *  approving moves no money — the info colour. Both used to share the
 *  warning, so a dot that was amber over 39 rows to approve read as "a
 *  category is missing" on an account with none missing. `pending`: rows on
 *  their way in from the bank and nothing else — a muted ring. Null: nothing
 *  to say. */
export type AttentionLevel = 'categorize' | 'approve' | 'pending'

export function attentionLevel(c: AttentionCounts): AttentionLevel | null {
  if (c.uncategorized_count > 0) return 'categorize'
  if (c.unapproved_count > 0) return 'approve'
  if (c.pending_count > 0) return 'pending'
  return null
}

/** The dot's accessible name and tooltip: "3 to categorize · 5 to approve ·
 *  2 pending". Only the parts that are not zero. */
export function attentionSummary(c: AttentionCounts): string {
  const parts = [
    c.uncategorized_count > 0 ? `${c.uncategorized_count} to categorize` : null,
    c.unapproved_count > 0 ? `${c.unapproved_count} to approve` : null,
    c.pending_count > 0 ? `${c.pending_count} pending` : null,
  ]
  return parts.filter(Boolean).join(' · ')
}
