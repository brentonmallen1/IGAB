import { describe, expect, it } from 'vitest'
import { otherIncome } from './incomeSourcesView'

describe('the Other income band', () => {
  it('keeps a genuine cent that float subtraction puts just under 0.01', () => {
    // 1000.01 − (600 + 400) is 0.00999… in floating point; `>= 0.01` lost it.
    expect(otherIncome(1000.01, [600, 400])).toBeCloseTo(0.01, 10)
  })

  it('draws no band for float dust above zero', () => {
    // `rest > 0` gave every month a phantom source worth $0.00.
    expect(otherIncome(0.3, [0.1, 0.2])).toBeNull()
    expect(otherIncome(1000, [600, 399.9999999])).toBeNull()
  })

  it('draws no band when the shown sources are the whole month, or over it', () => {
    expect(otherIncome(1000, [600, 400])).toBeNull()
    expect(otherIncome(1000, [600, 400.01])).toBeNull()
  })

  it('carries the rest when payees beyond the shown series paid something', () => {
    expect(otherIncome(6250, [6000])).toBe(250)
  })
})
