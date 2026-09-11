import { describe, expect, it } from 'vitest'
import { incomeSourceCount, otherIncome } from './incomeSourcesView'

describe('the Other income band', () => {
  it('keeps a genuine cent that float subtraction puts just under 0.01', () => {
    // 1000.01 − (600 + 400) is 0.00999… in floating point; `>= 0.01` lost it.
    expect(otherIncome(1000.01, [600, 400])).toBeCloseTo(0.01, 10)
  })

  it('draws no band for float dust on either side of zero', () => {
    // `rest > 0` gave every month a phantom source worth $0.00.
    expect(otherIncome(0.3, [0.1, 0.2])).toBeNull()
    expect(otherIncome(1000, [600, 399.9999999])).toBeNull()
    expect(otherIncome(1000, [600, 400.0000001])).toBeNull()
  })

  it('draws no band when the shown sources are the whole month', () => {
    expect(otherIncome(1000, [600, 400])).toBeNull()
  })

  it('carries the rest when payees beyond the shown series paid something', () => {
    expect(otherIncome(6250, [6000])).toBe(250)
  })

  it('carries a negative rest rather than dropping it', () => {
    // Northwind Payserv paid 3,000 and a −75 reconciliation adjustment was
    // filed to Ready to Assign under a payee outside the shown series. `rest >
    // 0` dropped the 75, so the stack stood at 3,000 over a table whose All
    // row read 2,925.
    expect(otherIncome(2925, [3000])).toBe(-75)
    // A whole cent the other way is a band too, not a rounding artifact.
    expect(otherIncome(1000, [600, 400.01])).toBeCloseTo(-0.01, 10)
  })
})

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
