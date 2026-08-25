/**
 * The post-import cache sweep. Every key here maps to a "works after I
 * refresh" bug when missing — `['transactions']` does not prefix-match
 * `['all-transactions']`, new payees rendered "—" for a minute, and a fresh
 * budget import didn't show in the selector. If a query moves to a new root
 * key, this list (and this test) must move with it.
 */
import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import { invalidateAfterImport } from './invalidateAfterImport'

const EXPECTED_ROOTS = [
  'transactions',
  'all-transactions',
  'budget-transactions',
  'category-transactions',
  'payee-transactions',
  'accounts',
  'payees',
  'pending-review-count',
  'pending-review-count-account',
  'pending-matches-account',
  'account-hygiene',
  'liabilities',
  'reconcile-status',
  'budgetMonth',
  'budgets',
]

describe('invalidateAfterImport', () => {
  it('invalidates every cache an import can touch', async () => {
    const qc = new QueryClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    await invalidateAfterImport(qc, 'b1')

    const roots = spy.mock.calls.map((c) => (c[0]!.queryKey as unknown[])[0])
    for (const root of EXPECTED_ROOTS) {
      expect(roots, `missing invalidation for ['${root}']`).toContain(root)
    }
  })

  it('scopes budgetMonth to the budget when known', async () => {
    const qc = new QueryClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    await invalidateAfterImport(qc, 'b1')
    expect(spy.mock.calls.some((c) => {
      const key = c[0]!.queryKey as unknown[]
      return key[0] === 'budgetMonth' && key[1] === 'b1'
    })).toBe(true)
  })

  it('reaches the budgets list even when its query is inactive', async () => {
    const qc = new QueryClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    await invalidateAfterImport(qc, null)
    const budgetsCall = spy.mock.calls.find(
      (c) => (c[0]!.queryKey as unknown[])[0] === 'budgets'
    )
    // Plain invalidation only refetches ACTIVE queries; right after an import
    // the user is navigating, so the selector's query is often not mounted.
    expect(budgetsCall![0]).toMatchObject({ refetchType: 'all' })
  })
})
