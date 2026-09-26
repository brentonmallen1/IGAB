import { describe, expect, it } from 'vitest'
import type { WishlistDisciplineReport } from '../../../types'
import {
  afterTheWait,
  averageWaitSub,
  waitedOutShare,
  wishCount,
  wishes,
  wishlistOutcomes,
} from './wishlistOutcomes'

function report(over: Partial<WishlistDisciplineReport> = {}): WishlistDisciplineReport {
  return {
    cooled_then_bought: 0,
    cooled_then_dropped: 0,
    bought_early: 0,
    dropped_early: 0,
    still_open: 0,
    ready_to_decide: 0,
    still_cooling: 0,
    decided_count: 0,
    waited_out_count: 0,
    waited_out_share: null,
    resisted_total: 0,
    resisted_count: 0,
    bought_total: 0,
    bought_count: 0,
    open_total: 0,
    avg_days_to_buy: null,
    avg_wish_cost: null,
    unplaced: 0,
    cooling_days: 30,
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
      still_cooling: 2,
      ready_to_decide: 3,
      unplaced: 2,
    })
    expect(wishlistOutcomes(d).reduce((s, r) => s + r.count, 0)).toBe(17)
    expect(new Set(wishlistOutcomes(d).map((r) => r.key)).size).toBe(7)
  })

  it('shows the unplaced row only when there are some', () => {
    expect(wishlistOutcomes(report()).some((r) => r.key === 'unplaced')).toBe(false)
    expect(wishlistOutcomes(report({ unplaced: 1 })).some((r) => r.key === 'unplaced')).toBe(true)
  })
})

describe('the open wishes', () => {
  it('split into those still in the wait and those ready to decide', () => {
    // "Still waiting" said neither: a wish past its wait waits on a decision.
    const rows = wishlistOutcomes(report({ still_open: 3, still_cooling: 1, ready_to_decide: 2 }))
    expect(rows.find((r) => r.key === 'still_cooling')?.count).toBe(1)
    expect(rows.find((r) => r.key === 'ready_to_decide')?.count).toBe(2)
    expect(rows.some((r) => r.key === 'still_open')).toBe(false)
  })
})

describe('the card words', () => {
  it('counts wishes grammatically', () => {
    // The card read "1 talked yourself out of".
    expect(wishes(1)).toBe('1 wish')
    expect(wishes(0)).toBe('0 wishes')
    expect(wishes(3)).toBe('3 wishes')
  })

  it('says the same two facts under Resisted and Bought', () => {
    expect(afterTheWait(4, 1)).toBe('4 wishes · 1 after the wait')
    expect(afterTheWait(1, 1)).toBe('1 wish · 1 after the wait')
  })

  it('states the headline share in whole percent, and none for nothing decided', () => {
    expect(waitedOutShare(0.75)).toBe('75%')
    expect(waitedOutShare(2 / 3)).toBe('67%')
    expect(waitedOutShare(0)).toBe('0%')
    expect(waitedOutShare(null)).toBe('—')
  })

  it('reads the average wait against the person’s own period', () => {
    expect(averageWaitSub(24, 30)).toBe('to buy · your wait is 30 days')
    expect(averageWaitSub(null, 14)).toBe('nothing bought yet · your wait is 14 days')
    expect(averageWaitSub(3, 1)).toBe('to buy · your wait is 1 day')
  })
})
