import { describe, expect, it } from 'vitest'
import { foldIncomeSources, rateFormula, TOP_INCOME_SOURCES } from './savingsRateBreakdown'

const src = (...totals: number[]) => totals.map((total, i) => ({ id: i, total }))

describe('rateFormula', () => {
  it('names the figures the dialog lists', () => {
    expect(rateFormula(false)).toBe('Saved ÷ Income')
    expect(rateFormula(true)).toBe('(Saved + Debt principal) ÷ Income')
  })
})

describe('foldIncomeSources', () => {
  it('folds nothing when every source fits', () => {
    const sources = src(3000, 2000)
    expect(foldIncomeSources(sources, 5000)).toEqual({ shown: sources, rest: null })
  })

  it('folds nothing at exactly the limit', () => {
    const sources = src(...Array.from({ length: TOP_INCOME_SOURCES }, () => 100))
    expect(foldIncomeSources(sources, 500).rest).toBeNull()
  })

  it('sums what it folds, so shown plus rest is the income', () => {
    const { shown, rest } = foldIncomeSources(src(3000, 800, 500, 300, 200, 150, 50), 5000)
    expect(shown.map((s) => s.total)).toEqual([3000, 800, 500, 300, 200])
    expect(rest).toEqual({ count: 2, total: 200 })
  })

  it('reads the remainder in cents, not float dust', () => {
    // 1000.01 − 1000 is 0.00999… in floating point.
    const { rest } = foldIncomeSources(src(600, 400, 0.01), 1000.01, 2)
    expect(rest?.count).toBe(1)
    expect(rest?.total).toBeCloseTo(0.01, 10)
  })

  it('keeps a negative remainder — a clawback past the fold', () => {
    const { rest } = foldIncomeSources(src(3000, -75), 2925, 1)
    expect(rest).toEqual({ count: 1, total: -75 })
  })

  it('reads folded sources that cancel as zero, not as missing', () => {
    const { rest } = foldIncomeSources(src(3000, 400, -400), 3000, 1)
    expect(rest).toEqual({ count: 2, total: 0 })
  })
})
