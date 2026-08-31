import type { QueryClient } from '@tanstack/react-query'
import { ROOT } from './queryKeys'

/**
 * Every cache an import can have made stale, in one place.
 *
 * An import touches more of the app than any single mutation: transactions in
 * bulk, accounts and their balances, payees it created, budget math, hygiene
 * counts, and — for a budget import — the budget list itself. Each import
 * surface used to keep its own shorter list, and each shortage was a
 * "works after I refresh the page" bug: `['transactions']` does not prefix-match
 * `['all-transactions']`, and freshly created payees rendered as "—" until
 * their 60s staleTime lapsed.
 *
 * Per-mutation hooks (useUpdateTransaction and friends) keep their narrower
 * targeted lists — they know which account changed. An import doesn't, so it
 * pays for the broad sweep.
 *
 * A snapshot restore widened this again: it is the first operation that can
 * replace a budget's guide state, wishlist, views, filters, tags and
 * schedules, so those roots live here rather than in a second, shorter list
 * at the new call site.
 *
 * `refetchType: 'all'` on the keys a navigation lands on next: invalidation
 * alone only refetches ACTIVE queries, and right after an import the user is
 * usually navigating — the budget selector after a budget import was the
 * canonical "still not there until I refresh" report.
 */
export function invalidateAfterImport(qc: QueryClient, budgetId: string | null): Promise<void> {
  const roots = [
    [ROOT.transactions],
    [ROOT.allTransactions],
    [ROOT.budgetTransactions],
    [ROOT.transactionsPeek],
    [ROOT.payeeTransactions],
    [ROOT.accounts],
    [ROOT.payees],
    [ROOT.pendingReviewCount],
    [ROOT.pendingReviewCountAccount],
    [ROOT.pendingMatchesAccount],
    [ROOT.accountHygiene],
    [ROOT.liabilities],
    [ROOT.reconcileStatus],
    // A second import, or a snapshot restore, writes a new summary onto an
    // existing budget. This cache is staleTime: Infinity, so without this
    // line only a page reload ever replaced it.
    [ROOT.importSummary],
    // An import moves every chart. None of them were listed.
    [ROOT.reports],
    // A snapshot restore is the first operation that can change any of
    // these: it replaces the whole budget, not just its ledger.
    [ROOT.categories],
    [ROOT.tags],
    [ROOT.budgetFilters],
    [ROOT.budgetViews],
    [ROOT.scheduledTransactions],
    ...(budgetId
      ? [
          ['guide', budgetId],
          ['wishlist', budgetId],
        ]
      : [['guide'], ['wishlist']]),
    ...(budgetId ? [['budgetMonth', budgetId]] : [['budgetMonth']]),
  ]
  return Promise.all([
    ...roots.map((queryKey) => qc.invalidateQueries({ queryKey })),
    qc.invalidateQueries({ queryKey: [ROOT.budgets], refetchType: 'all' }),
  ]).then(() => undefined)
}
