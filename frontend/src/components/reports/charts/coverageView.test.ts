import { describe, expect, it } from 'vitest'
import {
  carriedFlatFrom,
  coverageTrend,
  monthsCovered,
  monthsTick,
  monthsToTarget,
  standing,
} from './coverageView'
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
    expect(trend).toEqual({ from: 1.2, to: 3.4, delta: 2.2, months: 3 })
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
    // `months` is the span MEASURED, not the window asked for: the null
    // point is dropped, so this reading covers two months and the card must
    // not label it with the twelve the user picked.
    expect(trend).toEqual({ from: 2, to: 4, delta: 2, months: 2 })
  })

  it('spans a gap between its endpoints rather than counting it out', () => {
    // January 2.0 to April 4.0 is four months; counting known points said two.
    const janToApr = coverageTrend([
      point({ month: '2026-01-01', coverage_months: 2 }),
      point({ month: '2026-02-01', coverage_months: null }),
      point({ month: '2026-03-01', coverage_months: null }),
      point({ month: '2026-04-01', coverage_months: 4 }),
    ])
    expect(janToApr).toEqual({ from: 2, to: 4, delta: 2, months: 4 })
    const janToMar = coverageTrend([
      point({ coverage_months: 2 }),
      point({ coverage_months: null }),
      point({ coverage_months: 4 }),
    ])
    expect(janToMar?.months).toBe(3)
  })

  it('does not count a gap at the end either', () => {
    const trend = coverageTrend([
      point({ coverage_months: 1 }),
      point({ coverage_months: 3 }),
      point({ coverage_months: null }),
    ])
    expect(trend).toEqual({ from: 1, to: 3, delta: 2, months: 2 })
  })

  it('says nothing when no point, or only one, has an answer', () => {
    expect(coverageTrend([point({ coverage_months: null })])).toBeNull()
    expect(
      coverageTrend([point({ coverage_months: null }), point({ coverage_months: 2 })])
    ).toBeNull()
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

describe('where the self-reported fund is carried flat from', () => {
  it('names the first month that counts it, not the day it was saved', () => {
    // Saved on 2026-09-11: the served stamp is September, but the series ends
    // at August and August is the only point that counts the figure.
    const series = [
      point({ month: '2026-07-01', external_counted: false }),
      point({ month: '2026-08-01', external_counted: true }),
    ]
    expect(carriedFlatFrom(series)).toBe('2026-08-01')
  })

  it('is null when no point counts a self-reported figure', () => {
    expect(carriedFlatFrom([point({ external_counted: false })])).toBeNull()
  })
})

/** The first chart's axis is months of runway. Its tooltip formatter was
 * module-private in the component and untested, so going back to
 * `formatter={formatMoney}` — which read 3.4 months as "$3.40" — passed every
 * check. */
describe('monthsCovered', () => {
  it('reads months, not money', () => {
    expect(monthsCovered(3.4)).toBe('3.4 months')
    expect(monthsCovered(6)).toBe('6.0 months')
    expect(monthsCovered(3.4)).not.toContain('$')
  })

  it('ticks the axis with a bare count', () => {
    expect(monthsTick(3)).toBe('3')
  })
})
