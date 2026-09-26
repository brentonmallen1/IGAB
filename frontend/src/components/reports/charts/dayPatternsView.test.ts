import { describe, expect, it } from 'vitest'
import type { DayPatternItem } from '../../../types'
import { busiestAndQuietest, paydayBars, paydayPeak, shortDay } from './dayPatternsView'

const day = (i: number, total: number, weekdays: number): DayPatternItem => ({
  day_of_week: i,
  day_name: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][i],
  total,
  count: 1,
  weekdays,
  avg_per_day: weekdays ? total / weekdays : null,
})

describe('busiestAndQuietest', () => {
  it('ranks by a typical day, not by the window total', () => {
    // Five Saturdays at 100 and four Sundays at 110: Saturday has the larger
    // total and the smaller typical day. The chart ranked the totals.
    const days = [day(5, 500, 5), day(6, 440, 4)]
    const { busiest, quietest } = busiestAndQuietest(days)!
    expect(busiest.day_name).toBe('Sunday')
    expect(quietest.day_name).toBe('Saturday')
  })

  it('is nothing for a week with nothing spent', () => {
    expect(busiestAndQuietest([day(0, 0, 4), day(1, 0, 4)])).toBeNull()
  })

  it('skips a weekday the window does not hold', () => {
    const { quietest } = busiestAndQuietest([day(0, 50, 1), day(1, 0, 0)])!
    expect(quietest.day_name).toBe('Monday')
  })
})

describe('shortDay', () => {
  it('fits seven bars on a phone', () => {
    expect(shortDay('Wednesday')).toBe('Wed')
  })
})

describe('payday bars', () => {
  const days = [
    { offset: 0, median_spend: 40, paydays: 26 },
    { offset: 1, median_spend: 12, paydays: 26 },
    { offset: 2, median_spend: 12.5, paydays: 25 },
  ]

  it('marks the days above a typical day, and none without one', () => {
    expect(paydayBars(days, 12).map((b) => b.aboveBaseline)).toEqual([true, false, true])
    expect(paydayBars(days, null).some((b) => b.aboveBaseline)).toBe(false)
  })

  it('names payday itself', () => {
    expect(paydayBars(days, 12).map((b) => b.name)).toEqual(['Payday', '+1', '+2'])
  })

  it('finds the peak median', () => {
    expect(paydayPeak(days)?.offset).toBe(0)
    expect(paydayPeak([])).toBeNull()
  })
})
