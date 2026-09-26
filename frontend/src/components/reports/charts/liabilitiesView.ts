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
 *  and it names every row it leaves out: for want of terms, and because the
 *  minimum never pays that debt off, so there is no interest bill to add. */
export function interestRemainingSub(missingTerms: number, neverPaying: number): string {
  const parts = ['At minimum payments']
  if (missingTerms > 0) parts.push(`excludes ${missingTerms} without terms`)
  if (neverPaying === 1) parts.push('excludes 1 debt that never pays off at its payment')
  else if (neverPaying > 1) {
    parts.push(`excludes ${neverPaying} debts that never pay off at their payments`)
  }
  return parts.join(' · ')
}

/** The payoff warning, naming the payment it was measured at (`payoff_basis`).
 *  "At current pace" is true only with a pace — two months of payments.
 *  Without one the verdict is the minimum payment's, and it said "current
 *  pace" anyway. */
export function neverPaysOffWarning(basis: 'observed' | 'minimum' | null): string {
  return basis === 'observed'
    ? "Won't pay off at current pace"
    : "Won't pay off at the minimum payment"
}
