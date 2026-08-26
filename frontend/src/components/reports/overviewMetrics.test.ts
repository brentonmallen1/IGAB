import { describe, expect, it } from 'vitest'
import {
  clampedSavingsRate,
  essentialsReserve,
  netWorthDelta,
  roundedDaysUntilZero,
  spendingDelta,
} from './overviewMetrics'

describe('netWorthDelta', () => {
  it('is the percent change vs the prior period', () => {
    expect(netWorthDelta(1100, 1000)).toBeCloseTo(10)
    expect(netWorthDelta(900, 1000)).toBeCloseTo(-10)
  })

  it('uses an absolute denominator so recovering from debt reads positive', () => {
    // -500 -> -250: halved the hole. A signed denominator would call this -50%.
    expect(netWorthDelta(-250, -500)).toBeCloseTo(50)
  })

  it('is 0 when there is no prior value to compare', () => {
    expect(netWorthDelta(1000, 0)).toBe(0)
  })
})

describe('spendingDelta', () => {
  it('is the percent change in spending', () => {
    expect(spendingDelta(120, 100)).toBeCloseTo(20)
    expect(spendingDelta(80, 100)).toBeCloseTo(-20)
  })

  it('is 0 without prior spending', () => {
    expect(spendingDelta(120, 0)).toBe(0)
  })
})

describe('clampedSavingsRate', () => {
  it('converts the rate to a percentage', () => {
    expect(clampedSavingsRate(0.25)).toBe(25)
  })

  it('clamps overspent periods at 0 instead of showing a negative rate', () => {
    expect(clampedSavingsRate(-0.4)).toBe(0)
  })
})

describe('roundedDaysUntilZero', () => {
  it('rounds to whole days and passes null through', () => {
    expect(roundedDaysUntilZero('45.6')).toBe(46)
    expect(roundedDaysUntilZero(45.4)).toBe(45)
    expect(roundedDaysUntilZero(null)).toBeNull()
    expect(roundedDaysUntilZero(undefined)).toBeNull()
  })
})

describe('essentialsReserve', () => {
  it('multiplies the monthly figure by the months of runway', () => {
    expect(essentialsReserve(1200, 6)).toBe(7200)
  })

  it('has no answer until something is tagged', () => {
    expect(essentialsReserve(null, 6)).toBeNull()
    expect(essentialsReserve(undefined, 3)).toBeNull()
  })
})
