import { describe, expect, it } from 'vitest'
import { incomeSourceCount } from './incomeSourcesView'

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
