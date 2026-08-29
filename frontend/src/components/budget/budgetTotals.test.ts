import { describe, expect, it } from 'vitest'
import { sumBalances } from './budgetTotals'
import type { CategoryBalance } from '../../types'

function bal(assigned: number, activity: number, available: number): CategoryBalance {
  return {
    category_id: 'c1',
    month: '2026-08-01',
    assigned,
    activity,
    available,
    target_status: null,
    needed_this_month: null,
  is_card_payment: false,
  refused_card_inflows: 0,
  }
}

describe('sumBalances', () => {
  it('is all zeroes for an empty set', () => {
    expect(sumBalances([])).toEqual({ assigned: 0, activity: 0, available: 0, carriedOver: 0 })
  })

  it('carries nothing when available is exactly this month', () => {
    // assigned 100, spent 30, available 70 — nothing came from last month.
    expect(sumBalances([bal(100, -30, 70)]).carriedOver).toBe(0)
  })

  it('finds money that came in from last month', () => {
    // available exceeds assigned + activity by 50.
    expect(sumBalances([bal(100, -30, 120)]).carriedOver).toBe(50)
  })

  it('reports a negative carryover when available falls short', () => {
    expect(sumBalances([bal(100, 0, 60)]).carriedOver).toBe(-40)
  })

  it('sums across categories before inverting', () => {
    const totals = sumBalances([bal(100, -30, 120), bal(50, -10, 40)])
    expect(totals).toEqual({ assigned: 150, activity: -40, available: 160, carriedOver: 50 })
  })

  it('leaves an income row out entirely — its activity is income, not spending', () => {
    const income = { ...bal(0, 3100, 0), assigned: null, available: null }
    expect(sumBalances([bal(100, -30, 120), income])).toEqual({
      assigned: 100,
      activity: -30,
      available: 120,
      carriedOver: 50,
    })
  })

  it('handles decimal strings from the API', () => {
    const asStrings = [
      { ...bal(0, 0, 0), assigned: '10.50', activity: '-2.25', available: '8.25' },
    ] as unknown as CategoryBalance[]
    expect(sumBalances(asStrings).carriedOver).toBe(0)
  })
})
