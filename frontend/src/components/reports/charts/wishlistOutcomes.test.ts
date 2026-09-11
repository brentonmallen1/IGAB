import { describe, expect, it } from 'vitest'
import type { WishlistDisciplineReport } from '../../../types'
import { wishCount, wishlistOutcomes } from './wishlistOutcomes'

function report(over: Partial<WishlistDisciplineReport> = {}): WishlistDisciplineReport {
  return {
    cooled_then_bought: 0,
    cooled_then_dropped: 0,
    bought_early: 0,
    dropped_early: 0,
    still_open: 0,
    resisted_total: 0,
    resisted_count: 0,
    bought_total: 0,
    open_total: 0,
    avg_days_to_buy: null,
    avg_wish_cost: null,
    unplaced: 0,
    ...over,
  }
}

describe('wishlistOutcomes', () => {
  it('has a row for a wish dropped before its wait was up', () => {
    // It used to have none: a $100 wish dropped on day three of thirty left
    // every row at 0 and the table one wish short.
    const rows = wishlistOutcomes(report({ dropped_early: 1 }))
    expect(rows.find((r) => r.key === 'dropped_early')?.count).toBe(1)
    expect(wishCount(report({ dropped_early: 1 }))).toBe(1)
  })

  it('partitions every wish: the rows sum to the wishes', () => {
    const d = report({
      cooled_then_dropped: 2,
      dropped_early: 3,
      cooled_then_bought: 4,
      bought_early: 1,
      still_open: 5,
      unplaced: 2,
    })
    expect(wishlistOutcomes(d).reduce((s, r) => s + r.count, 0)).toBe(17)
    expect(new Set(wishlistOutcomes(d).map((r) => r.key)).size).toBe(6)
  })

  it('shows the unplaced row only when there are some', () => {
    expect(wishlistOutcomes(report()).some((r) => r.key === 'unplaced')).toBe(false)
    expect(wishlistOutcomes(report({ unplaced: 1 })).some((r) => r.key === 'unplaced')).toBe(true)
  })
})
