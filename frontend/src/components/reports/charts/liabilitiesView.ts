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
