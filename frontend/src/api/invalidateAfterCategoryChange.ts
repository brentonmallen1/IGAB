import type { QueryClient } from '@tanstack/react-query'

/**
 * Every cache a category delete, restore or repair stales — in one list.
 *
 * Deleting a category used to invalidate `['categories']` and nothing else,
 * which is the narrowest possible answer to the widest possible change: the
 * delete moves money to Ready to Assign, empties a row of the grid, changes
 * what the register draws in the category column, and shifts the
 * needs-a-category badge. All of that stayed on screen at its old value until
 * something unrelated happened to refetch.
 *
 * One list rather than a set spelled out at each call site, for the reason
 * spelled out in CLAUDE.md: the copies drift, and a dropped key here is
 * invisible — the screen simply shows a number that was true a minute ago.
 * A unit test spies each key so removing one has to be deliberate.
 */
export function invalidateAfterCategoryChange(
  qc: QueryClient,
  budgetId: string | null
): Promise<void> {
  const roots = [
    // The grid and its money.
    ['categories'],
    ['categoryGroups'],
    ['categoryClassification'],
    // Ready to Assign, every category balance, every target status.
    ...(budgetId ? [['budgetMonth', budgetId]] : [['budgetMonth']]),
    // The register's category column, and the rows that just became
    // uncategorized (or moved).
    ['transactions'],
    ['all-transactions'],
    ['budget-transactions'],
    ['category-transactions'],
    ['payee-transactions'],
    // The needs-a-category badge counts exactly those rows.
    ['pending-review-count'],
    ['pending-review-count-account'],
    // A payee's default category and a scheduled transaction's category are
    // both cleared by the delete.
    ['payees'],
    ['scheduled-transactions'],
    // Saved views and filters lose their placements/selections.
    ['budgetViews'],
    ['budgetFilters'],
    // Every report that groups by category. (`integrity` is deliberately not
    // here: IntegrityPanel holds its report in local state and re-runs on
    // demand, so there is no cache to stale — listing it would be a dead key
    // of exactly the kind this file exists to avoid.)
    ['reports'],
    // Undoing shows up in the activity list — `changesKeys.all`.
    ['changes'],
  ]
  return Promise.all(roots.map((queryKey) => qc.invalidateQueries({ queryKey }))).then(
    () => undefined
  )
}
