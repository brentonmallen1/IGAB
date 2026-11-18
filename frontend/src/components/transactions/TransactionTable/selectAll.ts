import type { Transaction } from '../../../types'
import { mayActOnInBulk } from './bulkActionable'

/**
 * What the register's select-all checkbox selects next. Three steps:
 *
 * 1. nothing, or only some rows, selected → every row that is not reconciled
 * 2. every non-reconciled row selected → every row, reconciled included
 * 3. every row selected → nothing
 *
 * Reconciled rows are locked (bulkActionable.ts), so the first click selects
 * what the bulk actions can act on. The locked rows stay one more click away.
 *
 * A register with no unlocked rows skips step 1: its first click selects all.
 */
export function selectAllStep(
  rows: readonly Pick<Transaction, 'id' | 'cleared'>[],
  selected: ReadonlySet<string>
): Set<string> {
  if (rows.length > 0 && rows.every((t) => selected.has(t.id))) return new Set()
  const unlocked = rows.filter(mayActOnInBulk)
  if (unlocked.every((t) => selected.has(t.id))) return new Set(rows.map((t) => t.id))
  return new Set(unlocked.map((t) => t.id))
}
