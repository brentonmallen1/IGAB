import { describe, expect, it } from 'vitest'
import { incomeSourceCount, incomeSourceRows, NO_PAYEE_KEY } from './incomeSourcesView'

// The Other band's cases moved with the rule to `drillDownTotals.test.ts`.

describe('the Sources count', () => {
  it('counts a payee that paid the household', () => {
    expect(incomeSourceCount([{ total: 6000 }, { total: 250 }])).toBe(2)
  })

  it('does not count a payee whose window nets to nothing or less', () => {
    // One employer plus one −75 adjustment is one source, not two.
    expect(incomeSourceCount([{ total: 3000 }, { total: -75 }])).toBe(1)
    expect(incomeSourceCount([{ total: 3000 }, { total: 0 }])).toBe(1)
  })

  it('is zero when nothing was taken home', () => {
    expect(incomeSourceCount([])).toBe(0)
    expect(incomeSourceCount([{ total: -75 }])).toBe(0)
  })
})

describe('incomeSourceRows', () => {
  it('keys each source by payee id, and income with no payee by its own key', () => {
    const rows = incomeSourceRows([
      { payee_id: 'p1', payee_name: 'Payment', monthly: [100], total: 100 },
      { payee_id: 'p2', payee_name: 'Payment', monthly: [50], total: 50 },
      { payee_id: null, payee_name: 'No payee', monthly: [5], total: 5 },
    ])
    expect(rows.map((r) => r.key)).toEqual(['p1', 'p2', NO_PAYEE_KEY])
    expect(rows.map((r) => r.name)).toEqual(['Payment', 'Payment', 'No payee'])
  })
})
