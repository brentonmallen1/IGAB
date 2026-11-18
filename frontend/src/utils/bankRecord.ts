import type { Transaction } from '../types'

/** Whether the bank supplied (or later matched) this row. `has_sync_source`
 *  is the served flag; `sync_source` covers rows read before it was served.
 *  One rule for the bank glyph, the duplicate review and the manual glyph. */
export function hasBankRecord(txn: Pick<Transaction, 'has_sync_source' | 'sync_source'>): boolean {
  return txn.has_sync_source || !!txn.sync_source
}

/** A row the user typed in that no bank record backs. A manual row the bank
 *  later matched wears the bank glyph's Link2 instead — see BankRecordIcon. */
export function isUnmatchedManualEntry(
  txn: Pick<Transaction, 'created_via' | 'has_sync_source' | 'sync_source'>
): boolean {
  return txn.created_via === 'manual' && !hasBankRecord(txn)
}
