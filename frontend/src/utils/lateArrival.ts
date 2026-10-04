/**
 * The words for a row's budget month around an import — a late arrival that
 * counts in the import month, and an imported row from before it that moves
 * no envelope.
 *
 * Copy and presentation only. Which month a row counts in is served
 * (`Transaction.counts_in_month`, backend `txn_filters.BUDGET_MONTH`), and so
 * is whether it predates the import (`Transaction.predates_import`); neither
 * rule is re-derived here. Kept in one place because the register row and the
 * editor both say it.
 */
import type { Transaction } from '../types'
import { formatMonth } from './dates'

/** The server counts this row in a month other than its own — a late
 *  arrival. Compares two served facts; decides nothing. */
export function countsInAnotherMonth(txn: Pick<Transaction, 'date' | 'counts_in_month'>): boolean {
  return txn.counts_in_month.slice(0, 7) !== txn.date.slice(0, 7)
}

/** The register glyph's tooltip and accessible name for a late arrival. */
export function lateArrivalLabel(countsInMonth: string): string {
  return `Arrived after your import — counts in ${formatMonth(countsInMonth)}`
}

/** The editor's note on a late arrival. */
export function lateArrivalNote(countsInMonth: string): string {
  return `Dated before your budget started, but it arrived after your import, so it counts in ${formatMonth(countsInMonth)}, the month your budget starts.`
}

/** The editor's note on a row from before the import month. */
export const PREDATES_IMPORT_NOTE =
  "Dated before your budget started. Its money is already in YNAB's starting figures, so changing its category or amount moves no envelope."
