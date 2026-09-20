/**
 * The register's default order, client side.
 *
 * `shared/register_order_cases.json` is the same table the backend's
 * `test_register_order.py` runs against `REGISTER_LADDER`. The server orders
 * and paginates; this re-sorts the pages that have arrived. A disagreement
 * does not show up as a wrong list — it shows up as a row that moves as you
 * scroll, which is why the cases are shared rather than written twice.
 */
import { describe, expect, it } from 'vitest'
import cases from '../../../../../shared/register_order_cases.json'
import {
  DEFAULT_TRANSACTION_SORT,
  REGISTER_LADDER,
  compareByRegisterOrder,
  nextTransactionSort,
  registerRank,
} from './registerOrder'
import type { Transaction } from '../../../types'

function txn(overrides: Partial<Transaction> = {}): Transaction {
  return {
    id: 't1',
    account_id: 'a1',
    date: '2026-08-02',
    amount: -12.5,
    category_id: null,
    transfer_id: null,
    is_split: false,
    cleared: 'uncleared',
    approved: true,
    needs_category: false,
    ...overrides,
  } as unknown as Transaction
}

describe('the shared ladder', () => {
  it('is the one the cases are numbered against', () => {
    expect([...REGISTER_LADDER]).toEqual(cases.ladder)
  })

  it.each(cases.cases)('$note', ({ cleared, approved, needs_category, rank }) => {
    expect(
      registerRank(txn({ cleared: cleared as Transaction['cleared'], approved, needs_category }))
    ).toBe(rank)
  })
})

describe('compareByRegisterOrder', () => {
  const reconciled = txn({ id: 'r', cleared: 'reconciled', date: '2026-08-30' })
  const cleared = txn({ id: 'c', cleared: 'cleared', date: '2026-01-04' })
  const uncleared = txn({ id: 'u', cleared: 'uncleared', date: '2026-01-02' })
  const unapproved = txn({ id: 'n', cleared: 'cleared', approved: false, date: '2025-12-01' })
  const pending = txn({ id: 'p', cleared: 'pending', date: '2025-06-06' })

  it('sinks reconciled rows below everything, however recent', () => {
    // The reported ask: the newest row on the page is a reconciled one and it
    // still belongs at the bottom.
    const order = [reconciled, cleared, uncleared, unapproved, pending]
      .sort(compareByRegisterOrder)
      .map((t) => t.id)
    expect(order).toEqual(['p', 'n', 'u', 'c', 'r'])
  })

  it('is newest-first within a rung', () => {
    const older = txn({ id: 'old', cleared: 'reconciled', date: '2026-01-01' })
    const newer = txn({ id: 'new', cleared: 'reconciled', date: '2026-02-01' })
    expect([older, newer].sort(compareByRegisterOrder).map((t) => t.id)).toEqual(['new', 'old'])
  })

  it('breaks a same-date tie on id, so a bulk import does not reshuffle on refetch', () => {
    const a = txn({ id: 'a', cleared: 'cleared' })
    const b = txn({ id: 'b', cleared: 'cleared' })
    expect([a, b].sort(compareByRegisterOrder).map((t) => t.id)).toEqual(['b', 'a'])
    expect([b, a].sort(compareByRegisterOrder).map((t) => t.id)).toEqual(['b', 'a'])
  })
})

describe('nextTransactionSort', () => {
  it('starts a column at its natural direction', () => {
    expect(nextTransactionSort('date', 'state', 'desc')).toEqual({
      column: 'date',
      direction: 'desc',
    })
    expect(nextTransactionSort('payee', 'state', 'desc')).toEqual({
      column: 'payee',
      direction: 'asc',
    })
  })

  it('flips on the second click', () => {
    expect(nextTransactionSort('date', 'date', 'desc')).toEqual({
      column: 'date',
      direction: 'asc',
    })
  })

  it('returns to the default order on the third', () => {
    expect(nextTransactionSort('date', 'date', 'asc')).toEqual(DEFAULT_TRANSACTION_SORT)
  })

  it('completes the cycle for every sortable column', () => {
    // A one-way door on any single column is the bug this cycle exists to
    // avoid, so walk all of them rather than trusting the one above.
    for (const col of ['date', 'account', 'payee', 'category', 'memo', 'amount'] as const) {
      let sort: { column: string; direction: 'asc' | 'desc' } = { ...DEFAULT_TRANSACTION_SORT }
      for (let click = 0; click < 3; click++) {
        sort = nextTransactionSort(col, sort.column as never, sort.direction)
      }
      expect(sort).toEqual(DEFAULT_TRANSACTION_SORT)
    }
  })
})
