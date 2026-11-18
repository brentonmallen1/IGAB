import type { Transaction } from '../../../types'

/**
 * Which selected rows the register's actions may act on. One home for the
 * rule; it was spelled inline five times in TransactionTable and once more in
 * select-all, and the copies differed in whether a split line counts.
 *
 * Two facts decide it:
 *
 * - **Locked** — a reconciled row. The statement vouched for it, so nothing in
 *   the register changes it in bulk: delete skips it, approve skips it,
 *   duplicate skips it, and select-all leaves it for a second click.
 * - **A whole row** — not a split line. A line is acted on through its parent:
 *   duplicating one alone, opening it alone, making it repeat alone or turning
 *   it into a transfer would each tear it off the split.
 */

type Row = Pick<Transaction, 'cleared' | 'parent_transaction_id'>

export function isLocked(t: Pick<Transaction, 'cleared'>): boolean {
  return t.cleared === 'reconciled'
}

export function isWholeRow(t: Pick<Transaction, 'parent_transaction_id'>): boolean {
  return !t.parent_transaction_id
}

/** Bulk delete, bulk approve and select-all's first step: any unlocked row. */
export function mayActOnInBulk(t: Pick<Transaction, 'cleared'>): boolean {
  return !isLocked(t)
}

/** Duplicate, and the single-row Edit / Make transfer: an unlocked whole row.
 *  (Make Repeating copies a row's terms and changes nothing on it, so it asks
 *  only `isWholeRow`.) */
export function mayActOnAsRow(t: Row): boolean {
  return mayActOnInBulk(t) && isWholeRow(t)
}
