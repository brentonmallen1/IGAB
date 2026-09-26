import { describe, expect, it } from 'vitest'
import {
  daysUntilZeroCard,
  essentialsReserve,
  netWorthDelta,
  roundedDaysUntilZero,
  spendingDelta,
} from './overviewMetrics'

describe('daysUntilZeroCard', () => {
  it('states the runway in whole days', () => {
    expect(daysUntilZeroCard(45.6)).toEqual({
      value: '46d',
      sub: 'Cash at current 30-day burn',
      overdrawn: false,
    })
  })

  it('shows the card at 0 when cash is already gone, and says so', () => {
    // The server served None here and the card hid.
    expect(daysUntilZeroCard(0)).toEqual({
      value: '0 days',
      sub: 'Overdrawn: cash is at or below zero',
      overdrawn: true,
    })
    expect(daysUntilZeroCard('0.0')?.overdrawn).toBe(true)
  })

  it('does not call a few hours of cash overdrawn, though it rounds to 0d', () => {
    expect(daysUntilZeroCard(0.3)).toMatchObject({ value: '0d', overdrawn: false })
  })

  it('draws no card when nothing is burning', () => {
    expect(daysUntilZeroCard(null)).toBeNull()
    expect(daysUntilZeroCard(undefined)).toBeNull()
  })
})

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

  it('is null, not 0, without prior spending — there is nothing to compare', () => {
    // 0 would read "unchanged". The Spent card and the means dialog each
    // guarded this themselves beside a function that said 0; they, and both
    // burn-rate lines, now read the null.
    expect(spendingDelta(120, 0)).toBeNull()
    expect(spendingDelta(120, -30)).toBeNull()
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
