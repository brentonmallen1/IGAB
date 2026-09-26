import { describe, expect, it } from 'vitest'
import { formatMonthShortWithOptions } from './dates'
import { completeMonthRows, monthRange, reportMonthLabel, throughMonth } from './reportMonths'

const short = (m: string) => formatMonthShortWithOptions(m, 'mdy')

describe('completeMonthRows', () => {
  it('drops the running month, which feeds no average or headline', () => {
    const rows = [
      { month: '2026-07-01', partial_month: false },
      { month: '2026-08-01', partial_month: false },
      { month: '2026-09-01', partial_month: true },
    ]
    expect(completeMonthRows(rows).map((r) => r.month)).toEqual(['2026-07-01', '2026-08-01'])
  })

  it('is empty on a budget whose history starts this month', () => {
    expect(completeMonthRows([{ partial_month: true }])).toEqual([])
  })
})

describe('reportMonthLabel', () => {
  it('is the one short month label, "so far" on the running month', () => {
    expect(reportMonthLabel('2026-08-01', false, short)).toBe('Aug 26')
    expect(reportMonthLabel('2026-09-01', true, short)).toBe('Sep 26 so far')
  })

  it('never prints the ISO "2025-10" axes it replaced', () => {
    expect(reportMonthLabel('2025-10-01', false, short)).not.toMatch(/\d{4}-\d{2}/)
  })

  it('follows the budget date format', () => {
    expect(reportMonthLabel('2026-09-01', true, (m) => formatMonthShortWithOptions(m, 'ymd'))).toBe(
      '26 Sep so far'
    )
  })
})

describe('throughMonth / monthRange', () => {
  it('names the last complete month', () => {
    expect(throughMonth('2026-08-01', short)).toBe('through Aug 26')
    expect(throughMonth(null, short)).toBeNull()
  })

  it('names a range, or one month once', () => {
    expect(monthRange('2026-06-01', '2026-08-31', short)).toBe('Jun 26 – Aug 26')
    expect(monthRange('2026-08-01', '2026-08-31', short)).toBe('Aug 26')
    expect(monthRange(null, '2026-08-31', short)).toBeNull()
  })

  it('crosses a year', () => {
    expect(monthRange('2025-11-01', '2026-01-31', short)).toBe('Nov 25 – Jan 26')
  })
})
