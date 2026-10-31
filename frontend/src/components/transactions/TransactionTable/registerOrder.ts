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
  const entered = compareText(instantKey(b.created_at), instantKey(a.created_at))
  if (entered !== 0) return entered
  return compareText(b.id, a.id)
}

/**
 * A served timestamp as a string that sorts the way the instant does.
 *
 * The server omits the fraction when the microseconds are zero, so the raw
 * strings put `09:00:00Z` above `09:00:00.500000Z` (`Z` > `.`). The key is
 * the whole seconds since the epoch, zero-padded, then the fraction padded to
 * six digits — which also folds any offset into one instant. Kept as a string
 * rather than a `Date` because a `Date` stops at milliseconds and a bulk
 * import separates rows by microseconds.
 */
export function instantKey(timestamp: string | null | undefined): string {
  if (!timestamp) return ''
  const m = /^(.+?T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})?$/.exec(timestamp)
  if (!m) return timestamp
  const ms = Date.parse(`${m[1]}${m[3] ?? 'Z'}`)
  if (Number.isNaN(ms)) return timestamp
  const seconds = String(Math.floor(ms / 1000)).padStart(12, '0')
  return `${seconds}.${(m[2] ?? '').padEnd(6, '0').slice(0, 6)}`
}

/** Code-point order, which is how Postgres compares a uuid's hex: a locale
 *  collation is free to rank characters some other way. */
function compareText(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0
}

// ─── The ledger order: a register with a running balance ────────────────────

/**
 * The rungs that still want a person — pending, unfiled, unapproved — which are
 * the register's Pending and Needs Review sections. The client half of
 * `ATTENTION_RUNGS` in txn_filters.py; the shared table pins both.
 */
export const ATTENTION_RUNGS = REGISTER_LADDER.indexOf('uncleared')

/**
 * The order a register with a running balance pages in: the attention rungs
 * first, as in the ladder, then everything else by date alone. Below them the
 * ladder would put yesterday's uncleared row above last week's cleared one,
 * and a running total drawn in that order does not step from row to row.
 */
export function ledgerRank(t: Transaction): number {
  return Math.min(registerRank(t), ATTENTION_RUNGS)
}

/** The server's `order=ledger`, for re-sorting the pages that have loaded. */
export function compareByLedgerOrder(a: Transaction, b: Transaction): number {
  const rank = ledgerRank(a) - ledgerRank(b)
  if (rank !== 0) return rank
  return compareByDateDesc(a, b)
}

/**
 * The main list's rows that are safe to draw beside a running balance.
 *
 * In the ledger order the attention rows all arrive first, whatever their
 * date, and the rest arrive newest first. So an unapproved row from last year
 * that is not in the Needs Review section (a tracking account's, say) is
 * loaded long before its neighbours — drawn at its date, it would sit below a
 * gap, with a figure that does not follow from the row above it. Rows older
 * than the oldest date-ordered row loaded so far wait until paging reaches
 * them. Order is preserved, so this works under either date direction.
 */
export function withinLedgerFrontier(
  rows: Transaction[],
  loaded: Transaction[],
  hasNextPage: boolean
): Transaction[] {
  if (!hasNextPage) return rows
  let frontier: Transaction | null = null
  for (const t of loaded) {
    if (ledgerRank(t) !== ATTENTION_RUNGS) continue
    if (frontier === null || compareByDateDesc(t, frontier) > 0) frontier = t
  }
  if (frontier === null) return []
  const oldest = frontier
  return rows.filter((t) => compareByDateDesc(t, oldest) <= 0)
}

/**
 * Whether to fetch again without waiting for a scroll: nothing in date order
 * has arrived yet, so the main list is empty and the virtualizer's
 * near-the-bottom trigger has no rows to fire from.
 */
export function ledgerNeedsMore(loaded: Transaction[], hasNextPage: boolean): boolean {
  return hasNextPage && !loaded.some((t) => ledgerRank(t) === ATTENTION_RUNGS)
}

/**
 * The sort a register actually draws in, and whether its Balance column shows.
 *
 * With a running balance the default order is date, newest first — so the
 * header reads Date ▼, a click flips it, and the next returns to the default.
 * Any other header hides the column: a running total beside rows in payee
 * order is arithmetic about nothing. Without one, the store's sort is drawn
 * as it is, and nothing about today's register changes.
 */
export function registerView(
  ledger: boolean,
  column: TransactionSortColumn,
  direction: SortDirection
): { column: TransactionSortColumn; direction: SortDirection; showsBalance: boolean } {
  if (!ledger) return { column, direction, showsBalance: false }
  if (column === 'state') return { column: 'date', direction: 'desc', showsBalance: true }
  return { column, direction, showsBalance: column === 'date' }
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
