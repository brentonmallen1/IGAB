import { describe, expect, it } from 'vitest'
import type { IncomeSplitLine, IncomeSplitReport } from '../types'
import {
  RULE_TICKS,
  barGeometry,
  gapPhrase,
  lineDetail,
  perMonthDivisor,
  reasonChip,
  shares,
  tooUnfiled,
} from './incomeSplit'

const line = (over: Partial<IncomeSplitLine> = {}): IncomeSplitLine => ({
  category_id: 'c1',
  name: 'Groceries',
  group_name: 'Everyday',
  reason: 'essential',
  total: 0,
  count: 1,
  spread: false,
  as_paid: null,
  minimum: null,
  above_minimum: null,
  minimum_unknown: false,
  note: null,
  ...over,
})

/** $7,200 take-home: 58 / 24 (3.72 committed) / 12 / 2 / 4. */
function report(over: Partial<IncomeSplitReport> = {}): IncomeSplitReport {
  return {
    start_date: '2026-07-01',
    end_date: '2026-09-30',
    months: 3,
    whole_months: true,
    running: false,
    clamped: false,
    tagged: true,
    spread_on: true,
    income: 7200,
    needs: { total: 4176, lines: [] },
    wants: {
      total: 1728,
      committed: [line({ reason: 'cost_of_living', total: 268 })],
      chosen: [line({ reason: 'untagged', total: 1460 })],
    },
    savings_debt: { total: 864, saved: [], debt: [] },
    uncategorized: { total: 144, count: 12 },
    left_over: 288,
    strict: { needs: 4101, savings_debt: 939 },
    ...over,
  }
}

describe('shares', () => {
  it('rounds to whole percents that add up to 100', () => {
    const s = shares(report())!
    expect(s).toEqual({ needs: 58, wants: 24, savings: 12, uncategorized: 2, left: 4 })
  })

  it('gives the rounding remainder to the largest fractions', () => {
    // 1/3 each: 33 + 33 + 34, never 99.
    const s = shares(
      report({
        income: 300,
        needs: { total: 100, lines: [] },
        wants: { total: 100, committed: [], chosen: [] },
        savings_debt: { total: 100, saved: [], debt: [] },
        uncategorized: { total: 0, count: 0 },
        left_over: 0,
      })
    )!
    expect(s.needs + s.wants + s.savings + s.uncategorized + s.left).toBe(100)
  })

  it('lets outflows past income sum past 100', () => {
    const s = shares(report({ left_over: -504 }))!
    expect(s.left).toBe(-7)
  })

  it('is nothing to take a share of with no income', () => {
    expect(shares(report({ income: 0 }))).toBeNull()
  })
})

describe('gapPhrase', () => {
  it('states a distance, never a verdict', () => {
    expect(gapPhrase(58, 50)).toBe('8 pts over')
    expect(gapPhrase(24, 30)).toBe('6 pts under')
    expect(gapPhrase(21, 20)).toBe('1 pt over')
    expect(gapPhrase(50, 50)).toBe('on the rule')
  })
})

describe('barGeometry', () => {
  it('draws the committed part of Wants as its own segment, and the ticks at 50 and 80', () => {
    const bar = barGeometry(report())!
    const width = Object.fromEntries(
      bar.segments.map((s) => [s.key, Math.round(s.width * 100) / 100])
    )
    expect(width).toEqual({
      needs: 58,
      committed: 3.72,
      wants: 20.28,
      savings: 12,
      uncategorized: 2,
      left: 4,
    })
    expect(bar.ticks).toEqual([...RULE_TICKS])
    expect(bar.incomeAt).toBe(100)
    expect(bar.over).toBe(0)
  })

  it('runs past the income line when outflows did, rather than squeezing to fit', () => {
    // 62 + 33 + 12 = 107% of take-home.
    const bar = barGeometry(
      report({
        income: 1000,
        needs: { total: 620, lines: [] },
        wants: { total: 330, committed: [], chosen: [] },
        savings_debt: { total: 120, saved: [], debt: [] },
        uncategorized: { total: 0, count: 0 },
        left_over: -70,
      })
    )!
    expect(bar.over).toBe(70)
    expect(bar.incomeAt).toBeCloseTo(93.46, 2)
    expect(bar.ticks[0]).toBeCloseTo(46.73, 2)
    expect(bar.segments.find((s) => s.key === 'left')!.width).toBe(0)
  })
})

describe('tooUnfiled', () => {
  it('holds back the gaps once a quarter of take-home is unfiled', () => {
    expect(tooUnfiled(report())).toBe(false)
    expect(tooUnfiled(report({ uncategorized: { total: 1800, count: 40 } }))).toBe(true)
  })
})

describe('the words on a line', () => {
  const money = (n: number) => `$${n}`

  it('says a spread bill was paid in full and counted by the month', () => {
    expect(lineDetail(line({ spread: true, as_paid: 1752, total: 438 }), money)).toBe(
      '$1752 paid in this range, spread over 12 months'
    )
  })

  it('reads a debt against its minimum', () => {
    expect(lineDetail(line({ minimum: 325, above_minimum: 225 }), money)).toBe(
      'Minimum $325 a month today — $225 paid above it'
    )
    expect(lineDetail(line({ minimum: 325, above_minimum: 0 }), money)).toBe(
      'Minimum $325 a month today'
    )
    expect(lineDetail(line({ minimum_unknown: true }), money)).toBe('No minimum payment on file')
  })

  it("names a saved line by the Savings Rate's own reading", () => {
    expect(reasonChip(line({ reason: 'saved', note: 'held in a Savings envelope' }))).toBe(
      'Saved · held in a Savings envelope'
    )
    expect(reasonChip(line({ reason: 'debt_no_category' }))).toBe('Debt payment · no category')
  })
})

describe('perMonthDivisor', () => {
  it('states whole months per month, and anything else as a total', () => {
    expect(perMonthDivisor(report())).toBe(3)
    expect(perMonthDivisor(report({ whole_months: false, months: 0.72 }))).toBe(1)
    expect(perMonthDivisor(report({ months: 1 }))).toBe(1)
  })
})
