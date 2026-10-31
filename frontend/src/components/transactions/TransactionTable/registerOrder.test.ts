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
  ATTENTION_RUNGS,
  DEFAULT_TRANSACTION_SORT,
  REGISTER_LADDER,
  compareByDateDesc,
  compareByLedgerOrder,
  compareByRegisterOrder,
  instantKey,
  ledgerNeedsMore,
  ledgerRank,
  nextTransactionSort,
  registerRank,
  registerView,
  withinLedgerFrontier,
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

describe('the shared tiebreak', () => {
  const rows = cases.tiebreak.rows.map((r) =>
    txn({ id: r.id, date: r.date, created_at: r.created_at })
  )

  it('orders same-day rows the way the server and its running balance do', () => {
    // compareByDateDesc ignored created_at: same-day rows came back in uuid
    // order, which is random, while the window summed them by entry time.
    const order = [...rows]
      .reverse()
      .sort(compareByDateDesc)
      .map((t) => t.id)
    expect(order).toEqual(cases.tiebreak.newest_first)
  })

  it('reads a whole-second timestamp as below the same second plus a fraction', () => {
    // Raw, '...09:00:00Z' > '...09:00:00.500000Z' because 'Z' > '.'.
    expect(instantKey('2026-03-10T09:00:00Z') < instantKey('2026-03-10T09:00:00.500000Z')).toBe(
      true
    )
  })

  it('normalises an offset to the instant it names', () => {
    expect(instantKey('2026-03-10T04:00:00.000005-05:00')).toBe(
      instantKey('2026-03-10T09:00:00.000005Z')
    )
  })
})

describe('the ledger order', () => {
  it('collapses the same rungs the server does', () => {
    expect(ATTENTION_RUNGS).toBe(cases.attention_rungs)
  })

  it.each(cases.cases)('$note', ({ cleared, approved, needs_category, ledger_rank }) => {
    expect(
      ledgerRank(txn({ cleared: cleared as Transaction['cleared'], approved, needs_category }))
    ).toBe(ledger_rank)
  })

  it('puts settled rows in date order, whatever their state', () => {
    const reconciled = txn({ id: 'r', cleared: 'reconciled', date: '2026-08-30' })
    const uncleared = txn({ id: 'u', cleared: 'uncleared', date: '2026-08-02' })
    const cleared = txn({ id: 'c', cleared: 'cleared', date: '2026-08-10' })
    const unapproved = txn({ id: 'n', approved: false, date: '2025-01-01' })
    const order = [uncleared, reconciled, unapproved, cleared]
      .sort(compareByLedgerOrder)
      .map((t) => t.id)
    // The ladder would read n, u, c, r.
    expect(order).toEqual(['n', 'r', 'c', 'u'])
  })
})

describe('withinLedgerFrontier', () => {
  const recent = txn({ id: 'recent', cleared: 'cleared', date: '2026-08-20' })
  const frontier = txn({ id: 'frontier', cleared: 'reconciled', date: '2026-08-10' })
  // Paged first as an attention row, but older than anything dated yet.
  const oldUnapproved = txn({ id: 'old', approved: false, date: '2025-02-01' })
  const loaded = [oldUnapproved, recent, frontier]

  it('holds back a row older than the oldest dated row while more pages remain', () => {
    const shown = withinLedgerFrontier([recent, frontier, oldUnapproved], loaded, true)
    expect(shown.map((t) => t.id)).toEqual(['recent', 'frontier'])
  })

  it('draws everything once the last page is in', () => {
    const shown = withinLedgerFrontier([recent, frontier, oldUnapproved], loaded, false)
    expect(shown.map((t) => t.id)).toEqual(['recent', 'frontier', 'old'])
  })

  it('keeps the order it was given, so an ascending sort survives', () => {
    const shown = withinLedgerFrontier([frontier, recent], loaded, true)
    expect(shown.map((t) => t.id)).toEqual(['frontier', 'recent'])
  })

  it('draws nothing until a dated row has arrived', () => {
    expect(withinLedgerFrontier([oldUnapproved], [oldUnapproved], true)).toEqual([])
    expect(ledgerNeedsMore([oldUnapproved], true)).toBe(true)
    expect(ledgerNeedsMore(loaded, true)).toBe(false)
    expect(ledgerNeedsMore([oldUnapproved], false)).toBe(false)
  })
})

describe('registerView', () => {
  it('leaves the register exactly as it is with the running balance off', () => {
    expect(registerView(false, 'state', 'desc')).toEqual({
      column: 'state',
      direction: 'desc',
      showsBalance: false,
    })
    expect(registerView(false, 'date', 'asc')).toEqual({
      column: 'date',
      direction: 'asc',
      showsBalance: false,
    })
  })

  it('draws the default as Date, newest first, with the column', () => {
    expect(registerView(true, 'state', 'desc')).toEqual({
      column: 'date',
      direction: 'desc',
      showsBalance: true,
    })
  })

  it('keeps the column under either date direction and hides it under any other sort', () => {
    expect(registerView(true, 'date', 'asc').showsBalance).toBe(true)
    for (const column of ['payee', 'category', 'memo', 'amount', 'account'] as const) {
      expect(registerView(true, column, 'asc').showsBalance).toBe(false)
    }
  })

  it('cycles Date ▼ → ▲ → default from the drawn sort, not the stored one', () => {
    const shown = registerView(true, DEFAULT_TRANSACTION_SORT.column, 'desc')
    const flipped = nextTransactionSort('date', shown.column, shown.direction)
    expect(flipped).toEqual({ column: 'date', direction: 'asc' })
    expect(nextTransactionSort('date', flipped.column, flipped.direction)).toEqual(
      DEFAULT_TRANSACTION_SORT
    )
  })
})
