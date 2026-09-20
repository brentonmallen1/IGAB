import type { Transaction } from '../../../types'
import type { SortDirection, TransactionSortColumn } from '../../../stores/uiStore'

/**
 * The register's default order: state, not date.
 *
 * Reconciled rows are finished — nobody has to look at one again — and
 * interleaving hundreds of them by date buries the handful that still want
 * attention. So the top-down order is what needs doing, then what is waiting
 * on the bank, then what is settled:
 *
 *   pending → unfiled → unapproved → uncleared → cleared → reconciled
 *
 * This is the client half of `REGISTER_LADDER` in
 * `backend/src/igab/repositories/txn_filters.py`. Both halves must exist: the
 * server decides which rows a page contains (it orders and paginates), the
 * client re-sorts the pages it has loaded. `shared/register_order_cases.json`
 * is one table run by both suites, so the two cannot drift into showing a row
 * in one place and then another as you scroll.
 *
 * `needs_category` is read, never rebuilt — see reviewSection.ts for what
 * re-deriving that rule cost.
 */
export const REGISTER_LADDER = [
  'pending',
  'needs_category',
  'unapproved',
  'uncleared',
  'cleared',
  'reconciled',
] as const

/** Index into the ladder; one past the end for a state it does not know, so an
 *  unrecognized row sorts below everything rather than beside the settled ones. */
export function registerRank(t: Transaction): number {
  if (t.cleared === 'pending') return 0
  if (t.needs_category) return 1
  if (!t.approved) return 2
  if (t.cleared === 'uncleared') return 3
  if (t.cleared === 'cleared') return 4
  if (t.cleared === 'reconciled') return 5
  return REGISTER_LADDER.length
}

/**
 * The default comparator: rank, then newest first within a rung.
 *
 * `id` breaks the final tie for the same reason the server's ordering ends on
 * it — a bulk import gives thousands of rows one timestamp, and an unstable
 * order over those makes rows appear to swap places on every refetch.
 */
export function compareByRegisterOrder(a: Transaction, b: Transaction): number {
  const rank = registerRank(a) - registerRank(b)
  if (rank !== 0) return rank
  return compareByDateDesc(a, b)
}

/**
 * Newest first — the order the Pending and Needs Review sections keep.
 *
 * The ladder deliberately stops at the main section. Those two sections are
 * already defined by state, and ranking inside them would undo the one thing
 * reviewSection.ts exists to do: a row held through categorization must stay
 * where it is, and under the ladder it would drop a rung the instant the
 * category landed — sending the user hunting for the row they were editing.
 */
export function compareByDateDesc(a: Transaction, b: Transaction): number {
  const date = b.date.localeCompare(a.date)
  if (date !== 0) return date
  return b.id.localeCompare(a.id)
}

/** The order the register starts in, and the order a third click on a sorted
 *  header comes back to. One constant, so the initial state and the way back
 *  cannot come to mean different things. */
export const DEFAULT_TRANSACTION_SORT = { column: 'state', direction: 'desc' } as const satisfies {
  column: TransactionSortColumn
  direction: SortDirection
}

/** A column's own direction on first click: dates read newest-first, names
 *  and amounts read A→Z / low→high. */
function naturalDirection(col: TransactionSortColumn): SortDirection {
  return col === 'date' ? 'desc' : 'asc'
}

/**
 * What clicking a header does: its natural direction, then the other one,
 * then back to the default state order.
 *
 * The third step is not a flourish. The default belongs to no header, so
 * without it a column sort is a one-way door — the only way back to
 * "reconciled at the bottom" would be a reload.
 */
export function nextTransactionSort(
  clicked: TransactionSortColumn,
  current: TransactionSortColumn,
  direction: SortDirection
): { column: TransactionSortColumn; direction: SortDirection } {
  const natural = naturalDirection(clicked)
  if (current !== clicked) return { column: clicked, direction: natural }
  if (direction === natural) {
    return { column: clicked, direction: natural === 'asc' ? 'desc' : 'asc' }
  }
  return { ...DEFAULT_TRANSACTION_SORT }
}
