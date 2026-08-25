/**
 * The payee text for a transaction row, transfers included.
 *
 * Transfers name their destination — "Transfer : Savings", the way YNAB reads
 * — from the server-computed `counterpart_account_id` (COUNTERPART_ACCOUNT_ID
 * in backend txn_filters.py: the linked partner's account, falling back to the
 * account the transfer payee names). Every register/list payee cell renders
 * through here; the per-site `transfer_id ? 'Transfer'` rules this replaces
 * are what made linked legs lose their destination.
 */
export function transactionDisplayPayee(
  txn: {
    payee_id: string | null
    transfer_id?: string | null
    counterpart_account_id?: string | null
  },
  payeeMap: Map<string, string>,
  accountMap?: Map<string, string>
): string {
  const counterpartName = txn.counterpart_account_id
    ? accountMap?.get(txn.counterpart_account_id)
    : undefined
  // The server's counterpart wins over the payee text: after a retarget the
  // link is truth and a stale payee is exactly what this must not echo.
  if (counterpartName) return `Transfer : ${counterpartName}`
  const payeeName = txn.payee_id ? payeeMap.get(txn.payee_id) : undefined
  if (payeeName) return payeeName
  // A transfer whose destination we can't name (account list still loading,
  // payee missing) — say what it is rather than pretending it has no payee.
  if (txn.counterpart_account_id || txn.transfer_id) return 'Transfer'
  return '—'
}
