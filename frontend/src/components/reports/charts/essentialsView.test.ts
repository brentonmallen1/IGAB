import { describe, expect, it } from 'vitest'
import { columnTotal, shareOfLeanMonth, worstMonth } from './essentialsView'

describe('shareOfLeanMonth', () => {
  it('is the share of the lean-month total, not of the largest category', () => {
    expect(shareOfLeanMonth(540, 1000)).toBe(54)
  })

  it('is 0 when nothing is spent at all', () => {
    expect(shareOfLeanMonth(540, 0)).toBe(0)
  })
})

describe('worstMonth', () => {
  it('picks the most expensive month', () => {
    const worst = worstMonth([
      { month: '2026-06-01', total: 900 },
      { month: '2026-07-01', total: 1400 },
      { month: '2026-08-01', total: 1100 },
    ])
    expect(worst).toEqual({ month: '2026-07-01', total: 1400 })
  })

  it('returns null when no month saw spending', () => {
    expect(worstMonth([{ month: '2026-06-01', total: 0 }])).toBeNull()
    expect(worstMonth([])).toBeNull()
  })

  it('keeps the earlier month on a tie', () => {
    const worst = worstMonth([
      { month: '2026-06-01', total: 900 },
      { month: '2026-07-01', total: 900 },
    ])
    expect(worst?.month).toBe('2026-06-01')
  })
})

describe('columnTotal', () => {
  it('adds the column in cents, so the footer is the sum a reader checks on paper', () => {
    // A float reduce gives 0.30000000000000004 for these two.
    expect(columnTotal([{ total: 0.1 }, { total: 0.2 }])).toBe(0.3)
    expect(columnTotal([{ total: 33.33 }, { total: 33.33 }, { total: 33.34 }])).toBe(100)
  })

  it('is zero for an empty table', () => {
    expect(columnTotal([])).toBe(0)
  })
})
