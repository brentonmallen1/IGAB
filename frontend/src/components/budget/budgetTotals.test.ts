import { describe, expect, it } from 'vitest'
import { overspending, sumBalances } from './budgetTotals'
import { makeCategoryBalance } from '../../test-utils/factories'
import type { CategoryBalance } from '../../types'

function bal(assigned: number, activity: number, available: number): CategoryBalance {
  return makeCategoryBalance({ assigned, activity, available })
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

  it('sums the numbers the API now actually sends', () => {
    // This used to pass STRINGS through `as unknown as CategoryBalance[]` and
    // assert they summed — because the wire sent strings while the type said
    // number, and `sumBalances` coerced. The server serializes Decimal as a
    // JSON number now (`schemas/base.py`), enforced by the response-contract
    // suite, so the cast is gone and the coercion with it. A string arriving
    // here would produce NaN, which is the right kind of loud.
    expect(
      sumBalances([{ ...bal(0, 0, 0), assigned: 10.5, activity: -2.25, available: 8.25 }])
        .carriedOver
    ).toBe(0)
  })
})

describe('overspending', () => {
  it('answers with the whole red, not the cash part', () => {
    // The bug this replaced: the hero chip and the Assign dropdown's Cover
    // row each answered "how much is overspent" for themselves, one with the
    // cash-only total. Covering emptied both while the grid stayed red.
    expect(overspending({ total_overspent: 120, total_overspent_credit: 45 })).toEqual({
      total: 120,
      onCards: 45,
    })
  })

  it('treats the card figure as a part of the total, never a sibling', () => {
    // A month overspent entirely on cards is still overspent — the row that
    // read the cash total showed "$0.00, disabled" for exactly this month.
    const { total, onCards } = overspending({ total_overspent: 45, total_overspent_credit: 45 })
    expect(total).toBe(45)
    expect(onCards).toBeLessThanOrEqual(total)
  })

  it('reads zero from a month that has not loaded yet', () => {
    expect(overspending(undefined)).toEqual({ total: 0, onCards: 0 })
    expect(overspending(null)).toEqual({ total: 0, onCards: 0 })
  })
})
