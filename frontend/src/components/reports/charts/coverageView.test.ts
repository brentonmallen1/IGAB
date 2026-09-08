import { describe, expect, it } from 'vitest'
import { coverageTrend, monthsToTarget, standing } from './coverageView'
import type { CoveragePoint } from '../../../types'

const point = (over: Partial<CoveragePoint>): CoveragePoint => ({
  month: '2026-01-01',
  fund_balance: 0,
  essentials: 1000,
  coverage_months: 0,
  target_low: 3000,
  target_high: 6000,
  external_counted: false,
  ...over,
})

describe('the trend under the headline', () => {
  it('reads the first known point against the last', () => {
    const trend = coverageTrend([
      point({ coverage_months: 1.2 }),
      point({ coverage_months: 2 }),
      point({ coverage_months: 3.4 }),
    ])
    expect(trend).toEqual({ from: 1.2, to: 3.4, delta: 2.2 })
  })

  it('says nothing from a single point', () => {
    // "Up from itself" is not a sentence.
    expect(coverageTrend([point({ coverage_months: 3 })])).toBeNull()
  })

  it('skips months with no answer', () => {
    // A month with no essential spending has no coverage figure — it must not
    // be read as a month of zero coverage.
    const trend = coverageTrend([
      point({ coverage_months: null }),
      point({ coverage_months: 2 }),
      point({ coverage_months: 4 }),
    ])
    expect(trend).toEqual({ from: 2, to: 4, delta: 2 })
  })

  it('reports a fall as a negative delta', () => {
    expect(
      coverageTrend([point({ coverage_months: 4 }), point({ coverage_months: 2.5 })])?.delta
    ).toBe(-1.5)
  })
})

describe('where the fund stands against the band', () => {
  const band = [3, 6] as const

  it('places coverage below, within and above', () => {
    expect(standing(1.4, band)).toBe('below')
    expect(standing(3, band)).toBe('within')
    expect(standing(6, band)).toBe('within')
    expect(standing(7.2, band)).toBe('above')
  })

  it('has no answer without a fund', () => {
    // Not "below": the app has not been told what to look at, which is a
    // different thing from being underfunded.
    expect(standing(null, band)).toBe('none')
  })
})

describe('months to the low end of the band', () => {
  it('divides the gap by the window’s pace', () => {
    // $1,000 → $2,000 over four points is $333/mo; the gap to $3,000 is
    // $1,000, so three more months.
    const series = [
      point({ fund_balance: 1000 }),
      point({ fund_balance: 1400 }),
      point({ fund_balance: 1700 }),
      point({ fund_balance: 2000 }),
    ]
    expect(monthsToTarget(series)).toBe(3)
  })

  it('says nothing when the fund is not growing', () => {
    // "In ∞ months" is worse than saying nothing.
    expect(monthsToTarget([point({ fund_balance: 900 }), point({ fund_balance: 900 })])).toBeNull()
    expect(monthsToTarget([point({ fund_balance: 900 }), point({ fund_balance: 400 })])).toBeNull()
  })

  it('says nothing once the target is met', () => {
    const series = [point({ fund_balance: 2000 }), point({ fund_balance: 3200 })]
    expect(monthsToTarget(series)).toBeNull()
  })

  it('uses the whole window rather than the last step', () => {
    // One windfall month is not a pace, and dividing a gap by a windfall
    // promises a date nobody can keep.
    const series = [
      point({ fund_balance: 0 }),
      point({ fund_balance: 0 }),
      point({ fund_balance: 0 }),
      point({ fund_balance: 1500 }),
    ]
    // $500/mo across the window, not $1,500 — four months, not one.
    expect(monthsToTarget(series)).toBe(3)
  })
})
