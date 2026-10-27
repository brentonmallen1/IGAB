import type { PendingReviewCounts } from '../../api/transactions'
import { reviewBreakdown, reviewPhrase } from '../../components/accounts/pendingReview'
import type { DriftNotice } from './bankDriftNotice'

/**
 * What an account has waiting, as one list — the phone's notice pill and the
 * "Needs a look" sheet behind it.
 *
 * On a desktop these are three separate bands above the register: the review
 * banner, the duplicates banner, the bank's sentence under the balances. On a
 * phone the three stacked to 150px before the first row, so they fold into a
 * single pill in the header row. The facts are the same ones the bands read
 * (served counts, `bankDriftNotice`), and the wording is shared with them
 * (`pendingReview.ts`, `duplicatesPhrase`), so the pill cannot count what the
 * bands do not.
 *
 * Pure: facts in, a list out. Ranking a tone from them is presentation of
 * served facts, which the server never decides.
 */

export type NoticeKind = 'duplicates' | 'bank' | 'review'

/** `warning`: something is off and wants fixing. `info`: worth a look, no
 *  money is wrong — the same split as the sidebar's dot (accountAttention). */
export type NoticeTone = 'warning' | 'info'

export interface AccountNotice {
  kind: NoticeKind
  tone: NoticeTone
  title: string
  detail: string
}

export interface NoticeFacts {
  review: PendingReviewCounts | null | undefined
  /** Possible duplicates waiting on this account. */
  duplicates: number
  drift: DriftNotice | null
}

/** "2 possible duplicates" — the desktop banner's opening words too. */
export function duplicatesPhrase(count: number): string {
  return count === 1 ? '1 possible duplicate' : `${count} possible duplicates`
}

/**
 * Most pressing first: a duplicate counts money twice, a bank gap may mean
 * rows never arrived, and a row to review is only waiting on a look.
 */
export function accountNotices({ review, duplicates, drift }: NoticeFacts): AccountNotice[] {
  const notices: AccountNotice[] = []
  if (duplicates > 0) {
    notices.push({
      kind: 'duplicates',
      tone: 'warning',
      title: duplicatesPhrase(duplicates),
      detail: 'They may match transactions you entered by hand.',
    })
  }
  if (drift) {
    notices.push({
      kind: 'bank',
      // The sync's own verdict (bank_drift_is_fault): a gap the feed has not
      // caught up with is information, not a fault.
      tone: drift.tone === 'fault' ? 'warning' : 'info',
      title: 'Bank balance differs',
      detail: drift.text,
    })
  }
  if (review && review.total > 0) {
    notices.push({
      kind: 'review',
      // An unfiled row leaves the budget wrong; a row to approve does not.
      tone: review.uncategorized > 0 ? 'warning' : 'info',
      title: reviewPhrase(review.total),
      detail: reviewBreakdown(review),
    })
  }
  return notices
}

/** The pill's colour: the most urgent notice's, or null when there is none. */
export function noticesTone(notices: readonly AccountNotice[]): NoticeTone | null {
  if (notices.length === 0) return null
  return notices.some((n) => n.tone === 'warning') ? 'warning' : 'info'
}

/** The pill's accessible name: "2 things need a look: 2 possible duplicates,
 *  15 transactions to review". */
export function noticesLabel(notices: readonly AccountNotice[]): string {
  const head =
    notices.length === 1 ? '1 thing needs a look' : `${notices.length} things need a look`
  return `${head}: ${notices.map((n) => n.title).join(', ')}`
}
