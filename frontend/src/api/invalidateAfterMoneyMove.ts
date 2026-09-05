import type { QueryClient } from '@tanstack/react-query'
import { ROOT } from './queryKeys'

/**
 * Every cache that changes when assigned money moves — in one list.
 *
 * "Money moved" is one event with six spellings: typing in an Assigned cell,
 * the move-money popover, undoing one move, applying a bulk assign, applying
 * Cover Overspending, and undoing any of them. Each of those wrote its own
 * list, and the six lists had drifted to six different lengths:
 *
 *   assign apply           6 keys
 *   cover overspending     4
 *   undo one move          4
 *   move money             2
 *   set assignment         1
 *   undo (any of the above) 1  ← the one the user hit
 *
 * So an undo left the hero's strategy amounts, the Cover Overspending pill,
 * the preview table and the month's move list showing figures from the
 * operation that had just been taken back. `staleTime` on those queries kept
 * them wrong until something unrelated refetched.
 *
 * Not month-scoped, deliberately: assignments ripple forward — a July
 * assignment changes every later month's available and every month's Ready to
 * Assign — so the month segment is dropped and each root is staled whole.
 * `useSetAssignment` said as much in its own comment while scoping four of
 * its siblings to a single month.
 */
export function invalidateAfterMoneyMove(qc: QueryClient, budgetId: string): Promise<void> {
  const roots = [
    // The grid: every assigned, available and Ready to Assign figure.
    [ROOT.budgetMonth, budgetId],
    // The month's move list — undo drops rows from it, not just amounts.
    [ROOT.budgetMoves, budgetId],
    // The TBA hero's dropdown: one dollar amount per strategy, all of them
    // computed from the balances that just moved.
    [ROOT.assignStrategies, budgetId],
    // An open preview table is now describing a budget that no longer exists.
    [ROOT.assignPreview, budgetId],
    // The overspent pill and its dialog.
    [ROOT.coverOverspentPreview, budgetId],
    // Per-category assigned/spent history, which the target pills read from.
    [ROOT.categoryHistoryBatch, budgetId],
  ]
  return Promise.all(roots.map((queryKey) => qc.invalidateQueries({ queryKey }))).then(
    () => undefined
  )
}
