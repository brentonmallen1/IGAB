import type { QueryClient } from '@tanstack/react-query'
import { ROOT } from './queryKeys'

/**
 * Every cache a transaction change can have made stale, in one place.
 *
 * There were ten copies of this list — one per mutation in `transactions.ts`
 * plus one in `ReceiptScanTab` — and they had already drifted. The differences
 * were the bug list, and each is now a test case:
 *
 * - `account-hygiene` and `transaction-splits` were only in `useUpdateTransaction`
 * - `reconcile-status` was in three of the ten
 * - `useMergeTransactions` invalidated no pending-review count at all
 * - `useUnreconcileTransaction` refreshed neither `budgetMonth` nor `accounts`,
 *   so unreconciling left the register right and Ready to Assign wrong
 * - `transactions-peek` and `budget-transactions` — the category peek modal and
 *   the report drill-down — were in **none** of them. What every copy carried
 *   instead was `['category-transactions']`, which is not a query key anywhere
 *   and refreshed nothing. That is the whole "I had to reload the page" report.
 *
 * A comment asking ten call sites to stay in step is not a mechanism. This is.
 *
 * `accountId` narrows the register refetch to the account that changed, and
 * pending-review counts with it; omit it and both go wide, which is what a
 * bulk mutation spanning accounts wants. `transactionIds` covers the per-row
 * caches a single-row edit invalidates.
 */
export function invalidateAfterTransactionChange(
  qc: QueryClient,
  opts: { budgetId: string | null; accountId?: string | null; transactionIds?: string[] }
): Promise<void> {
  const { budgetId, accountId, transactionIds = [] } = opts

  const roots: unknown[][] = [
    // The register, and every other listing of the same rows.
    [ROOT.transactions],
    [ROOT.allTransactions],
    [ROOT.budgetTransactions],
    [ROOT.transactionsPeek],
    [ROOT.payeeTransactions],
    // Money. A row's amount, date or category moves all of these.
    [ROOT.budgetMonth, budgetId],
    [ROOT.accounts, budgetId],
    // The register creates payees by typing a name into one, so a payee list
    // can be stale after any write. `useMergeTransactions` was the only copy
    // that knew this.
    [ROOT.payees, budgetId],
    // A new or retargeted row changes what could be another row's far leg.
    // Only `useUpdateTransaction` carried this.
    [ROOT.transferCandidates],
    // Counts and status the header and the account list render.
    [ROOT.pendingReviewCount],
    [ROOT.reconcileStatus],
    [ROOT.accountHygiene, budgetId],
    ...(accountId
      ? [[ROOT.pendingReviewCountAccount, accountId]]
      : [[ROOT.pendingReviewCountAccount]]),
    // Per-row caches. A parent's date/cleared edit mirrors onto its lines, and
    // a category change rewrites the row's own classification.
    ...transactionIds.flatMap((id) => [
      [ROOT.transaction, id],
      [ROOT.transactionSplits, id],
      [ROOT.transactionClassification, id],
    ]),
  ]

  return Promise.all(roots.map((queryKey) => qc.invalidateQueries({ queryKey }))).then(
    () => undefined
  )
}
