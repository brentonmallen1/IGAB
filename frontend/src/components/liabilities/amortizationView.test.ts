import { describe, expect, it } from 'vitest'
import { groupByYear, scheduleTotals } from './amortizationView'

const month = (index: number, date: string, over: Record<string, number> = {}) => ({
  month_index: index,
  date,
  payment: 400,
  principal_paid: 390,
  interest_paid: 10,
  balance: 1000 - index * 390,
  ...over,
})

describe('groupByYear', () => {
  it('buckets by calendar year, in schedule order', () => {
    const years = groupByYear([
      month(1, '2026-11-01'),
      month(2, '2026-12-01'),
      month(3, '2027-01-01'),
    ])
    expect(years.map((y) => y.year)).toEqual([2026, 2027])
    expect(years[0].months).toHaveLength(2)
    expect(years[1].months).toHaveLength(1)
  })

  it('sums the year and carries its last balance', () => {
    const [y] = groupByYear([
      month(1, '2026-11-01', { balance: 610 }),
      month(2, '2026-12-01', { balance: 220 }),
    ])
    expect(y.payments).toBe(800)
    expect(y.principal).toBe(780)
    expect(y.interest).toBe(20)
    expect(y.endBalance).toBe(220) // the year's LAST month, not a sum
  })

  it('is empty for an empty schedule', () => {
    expect(groupByYear([])).toEqual([])
  })
})

describe('scheduleTotals', () => {
  it('sums the three money columns', () => {
    const totals = scheduleTotals([month(1, '2026-11-01'), month(2, '2026-12-01')])
    expect(totals).toEqual({ payments: 800, principal: 780, interest: 20 })
  })
})
