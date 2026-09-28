import type { LiabilitiesReportItem } from '../../../types'

/**
 * What the Liabilities report says about debt left on closed accounts.
 *
 * The server leaves a loan under a closed account out of `total_balance` and
 * counts it separately (`closed_with_balance_*`, already narrowed to the
 * report's type and mode filters). Pure, so each sentence is a one-line test.
 */

function closedAccounts(count: number): string {
  return count === 1 ? 'an account that has been closed' : `${count} accounts that have been closed`
}

/** The note under the metric cards, or in place of the empty state when the
 *  only debt in view sits on closed accounts. Null when there is none.
 *
 *  It used to render above the cards and say "not in the total above", and to
 *  sit beside "No liabilities tracked yet" when every debt was on a closed
 *  account. */
export function closedDebtNote(count: number, owed: string, empty: boolean): string | null {
  if (count <= 0) return null
  const settle = 'Reopen the account, or settle the balance, to bring the two figures together.'
  if (empty) {
    return (
      `No open liabilities here, but ${owed} is still owed on ${closedAccounts(count)}. ` +
      `Net worth still counts it. ${settle}`
    )
  }
  return (
    `${owed} is still owed on ${closedAccounts(count)}, so Total Liabilities leaves it out — ` +
    `but net worth still counts it. ${settle}`
  )
}

/** The Total Liabilities card's sub-label. "Every debt" is false while a
 *  closed account still owes something the total leaves out. */
export function totalLiabilitiesSub(closedCount: number): string {
  if (closedCount <= 0) return 'Every debt, cards included'
  const plural = closedCount === 1 ? 'account' : 'accounts'
  return `Cards included · excludes ${closedCount} closed ${plural}`
}

/** What a row says where its date and its interest would be when the minimum
 *  never retires the debt (`baseline_never_pays_off`). The interest cell used
 *  to say $0.00, and that $0 was added into the headline. */
export const NEVER_AT_THIS_PAYMENT = 'Never at this payment'

/** The Interest Remaining card's sub-label. The total is at minimum payments,
 *  and it names every row it leaves out: what the rows without terms owe —
 *  in dollars, since "excludes 2" said nothing about how much — and the debts
 *  the minimum never pays off, which have no interest bill to add. */
export function interestRemainingSub(
  missingTerms: number,
  missingTermsOwed: string,
  neverPaying: number
): string {
  const parts = ['At minimum payments']
  if (missingTerms > 0) parts.push(`excludes ${missingTermsOwed} without terms`)
  if (neverPaying === 1) parts.push('excludes 1 debt that never pays off at its payment')
  else if (neverPaying > 1) {
    parts.push(`excludes ${neverPaying} debts that never pay off at their payments`)
  }
  return parts.join(' · ')
}

/** The count card's sub-label: how many of the rows owe anything today. */
export function carryingSub(carrying: number, rows: number): string {
  if (carrying === rows) return carrying === 1 ? 'Carrying a balance' : 'All carrying a balance'
  return `${carrying} carrying a balance`
}

/** What the two payoff columns mean, said once: the column headers' titles,
 *  the note under the table and the ⓘ read these. They were "Contractual"
 *  and "Live payoff", defined nowhere. */
export const AT_MINIMUM = 'At minimum'
export const AT_MINIMUM_MEANS = 'paid off paying only the minimum payment'
export const AT_YOUR_PACE = 'At your pace'
export const AT_YOUR_PACE_MEANS =
  'paid off paying what a typical recent month has been — the median of the last six months’ payments'

type PaceMissing = LiabilitiesReportItem['pace_missing']

/** Why the "At your pace" cell has no date — the cell said "—" for all
 *  three (`liability_service.pace_missing`). */
export const PACE_MISSING: Record<NonNullable<PaceMissing>, { label: string; why: string }> = {
  no_terms: {
    label: 'No terms',
    why: 'Add the APR and minimum payment to project a payoff.',
  },
  payments_not_linked: {
    label: 'Payments not linked',
    why: 'Deposits on this account are not transfers from the paying account, so they are not counted as payments. Record payments as transfers.',
  },
  too_little_history: {
    label: 'Too little history',
    why: 'A pace needs at least two months with a payment.',
  },
}

/** The "At your pace" cell: a date, a warning, or why there is neither. */
export function paceCell(
  item: Pick<
    LiabilitiesReportItem,
    'payoff_basis' | 'never_pays_off' | 'live_payoff_date' | 'pace_missing'
  >,
  formatMonth: (d: string) => string
): { text: string; warning: boolean; why?: string } {
  if (item.payoff_basis === 'observed') {
    if (item.never_pays_off) return { text: "Won't pay off at your pace", warning: true }
    if (item.live_payoff_date) return { text: formatMonth(item.live_payoff_date), warning: false }
  }
  const reason = item.pace_missing ? PACE_MISSING[item.pace_missing] : null
  return reason
    ? { text: reason.label, warning: false, why: reason.why }
    : { text: '—', warning: false }
}

/** "Terms disagree", beside a row whose entered payment contradicts the
 *  payment its own principal, rate and term imply (`amortization.terms_check`)
 *  — the liability page carries the same flag. */
export const TERMS_DISAGREE = 'Terms disagree: the payment may include escrow'

/** Liabilities worth drawing: any whose balance is not zero somewhere in the
 *  window. A paid-off debt drew a flat line at zero and took a legend entry. */
export function drawnLiabilities<T extends { liability_id: string }>(
  items: T[],
  points: { per_liability: Record<string, number> }[]
): T[] {
  return items.filter((item) => points.some((p) => (p.per_liability[item.liability_id] ?? 0) !== 0))
}
