import { describe, expect, it } from 'vitest'
import type { IncomeExpenseMonth } from '../../../types'
import { windowTotals } from './incomeExpenseView'

function month(month: string, over: Partial<IncomeExpenseMonth> = {}): IncomeExpenseMonth {
  return {
    month,
    partial_month: false,
    income: 0,
    expenses: 0,
    savings: 0,
    savings_moved: 0,
    savings_held: 0,
    debt_principal: 0,
    net: 0,
    ...over,
  }
}

describe('windowTotals', () => {
  it('adds up the complete months, and names them', () => {
    const t = windowTotals([
      month('2026-07-01', { income: 5000, expenses: 3000, savings: 500, net: 1500 }),
      month('2026-08-01', { income: 5000, expenses: 3500, debt_principal: 400, net: 1100 }),
    ])
    expect(t).toEqual({
      income: 10000,
      expenses: 6500,
      savings: 500,
      debt_principal: 400,
      net: 2600,
      first: '2026-07-01',
      last: '2026-08-01',
    })
  })

  it('leaves the running month out: it is a row, never part of the total', () => {
    const t = windowTotals([
      month('2026-08-01', { income: 5000, net: 5000 }),
      month('2026-09-01', { partial_month: true, income: 2500, expenses: 4000, net: -1500 }),
    ])
    expect(t?.income).toBe(5000)
    expect(t?.net).toBe(5000)
    expect(t?.last).toBe('2026-08-01')
  })

  it('has no total with no complete month', () => {
    expect(windowTotals([])).toBeNull()
    expect(windowTotals([month('2026-09-01', { partial_month: true, income: 100 })])).toBeNull()
  })

  it('sums in cents, so a column of cents totals exactly', () => {
    const t = windowTotals([
      month('2026-07-01', { expenses: 0.1 }),
      month('2026-08-01', { expenses: 0.2 }),
    ])
    expect(t?.expenses).toBe(0.3)
  })

  it('keeps signs: a month that drew savings out and ran a deficit', () => {
    const t = windowTotals([
      month('2026-07-01', { savings: -1200, net: -3300, expenses: -40 }),
      month('2026-08-01', { savings: 200, net: 100, expenses: 900 }),
    ])
    expect(t).toMatchObject({ savings: -1000, net: -3200, expenses: 860 })
  })
})
