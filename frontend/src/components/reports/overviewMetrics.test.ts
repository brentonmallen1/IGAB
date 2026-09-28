import { describe, expect, it } from 'vitest'
import { periodHeading, runwayFallback, spendingDelta } from './overviewMetrics'
import { formatDayMonthWithOptions, formatMonthShortWithOptions } from '../../utils/dates'

describe('periodHeading', () => {
  const month = (m: string) => formatMonthShortWithOptions(m, 'mdy')
  const day = (d: string) => formatDayMonthWithOptions(d, 'mdy')

  it('names a whole past month by its month', () => {
    expect(periodHeading('2026-08-01', '2026-08-31', '2026-09-26', month, day)).toBe('Aug 26')
  })

  it('says "so far" on the running month', () => {
    expect(periodHeading('2026-09-01', '2026-09-26', '2026-09-26', month, day)).toBe(
      'Sep 26 so far'
    )
    // On the 1st the running month is one day long, and still so far.
    expect(periodHeading('2026-10-01', '2026-10-01', '2026-10-01', month, day)).toBe(
      'Oct 26 so far'
    )
  })

  it('names any other range by its days', () => {
    expect(periodHeading('2026-06-01', '2026-08-31', '2026-09-26', month, day)).toBe(
      'Jun 1 – Aug 31'
    )
    expect(periodHeading('2026-08-03', '2026-08-12', '2026-09-26', month, day)).toBe(
      'Aug 3 – Aug 12'
    )
    expect(periodHeading('2026-01-01', '2026-09-26', '2026-09-26', month, day)).toBe(
      'Jan 1 – Sep 26, so far'
    )
  })

  it('knows February', () => {
    expect(periodHeading('2028-02-01', '2028-02-29', '2028-03-05', month, day)).toBe('Feb 28')
  })
})

describe('runwayFallback', () => {
  it('says nothing when the card read its default', () => {
    expect(runwayFallback({ fund_chosen: true, essentials_known: true })).toBeNull()
  })

  it('says why the money fell back to checking', () => {
    expect(runwayFallback({ fund_chosen: false, essentials_known: true })).toBe(
      'No emergency fund chosen'
    )
  })

  it('says why the spending fell back to all of it', () => {
    expect(runwayFallback({ fund_chosen: true, essentials_known: false })).toBe(
      'Nothing tagged Essential'
    )
  })

  it('says both when both fell back', () => {
    expect(runwayFallback({ fund_chosen: false, essentials_known: false })).toBe(
      'Nothing tagged Essential, no emergency fund chosen'
    )
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
