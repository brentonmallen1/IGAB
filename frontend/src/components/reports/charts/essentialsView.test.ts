import { describe, expect, it } from 'vitest'
import { shareOfLeanMonth, worstMonth } from './essentialsView'

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
