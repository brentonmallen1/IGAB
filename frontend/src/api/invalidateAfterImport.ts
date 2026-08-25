import type { QueryClient } from '@tanstack/react-query'

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
 * `refetchType: 'all'` on the keys a navigation lands on next: invalidation
 * alone only refetches ACTIVE queries, and right after an import the user is
 * usually navigating — the budget selector after a budget import was the
 * canonical "still not there until I refresh" report.
 */
export function invalidateAfterImport(qc: QueryClient, budgetId: string | null): Promise<void> {
  const roots = [
    ['transactions'],
    ['all-transactions'],
    ['budget-transactions'],
    ['category-transactions'],
    ['payee-transactions'],
    ['accounts'],
    ['payees'],
    ['pending-review-count'],
    ['pending-review-count-account'],
    ['pending-matches-account'],
    ['account-hygiene'],
    ['liabilities'],
    ['reconcile-status'],
    ...(budgetId ? [['budgetMonth', budgetId]] : [['budgetMonth']]),
  ]
  return Promise.all([
    ...roots.map((queryKey) => qc.invalidateQueries({ queryKey })),
    qc.invalidateQueries({ queryKey: ['budgets'], refetchType: 'all' }),
  ]).then(() => undefined)
}
