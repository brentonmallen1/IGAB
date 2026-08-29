/**
 * The stored schedule is one list of UTC hours; these are the two readings a
 * person has of it. Nothing here decides when a sync runs — the server does —
 * so the only property that matters is that a schedule survives the round
 * trip through whichever control it opens in.
 */
import { describe, expect, it } from 'vitest'
import {
  INTERVAL_CHOICES,
  deriveInterval,
  hoursForInterval,
  localHourToUtcHour,
  utcHourToLocalHour,
} from './hourSchedule'

describe('hoursForInterval', () => {
  it('spreads the day evenly from the anchor', () => {
    expect(hoursForInterval(6, 0)).toEqual([0, 6, 12, 18])
    expect(hoursForInterval(6, 2)).toEqual([2, 8, 14, 20])
    expect(hoursForInterval(12, 7)).toEqual([7, 19])
  })

  it('wraps an anchor larger than the interval back into the first cycle', () => {
    // "every 4 hours starting at 9" is the same set as starting at 1
    expect(hoursForInterval(4, 9)).toEqual([1, 5, 9, 13, 17, 21])
  })

  it('never exceeds the daily rate limit at its densest', () => {
    expect(hoursForInterval(2, 0)).toHaveLength(12)
  })
})

describe('deriveInterval', () => {
  it('recognises an evenly spaced day', () => {
    expect(deriveInterval([0, 6, 12, 18])).toBe(6)
    expect(deriveInterval([2, 8, 14, 20])).toBe(6)
    expect(deriveInterval([7, 19])).toBe(12)
  })

  it('reads the list in any order', () => {
    expect(deriveInterval([18, 0, 12, 6])).toBe(6)
  })

  it('calls a set of chosen times what it is', () => {
    expect(deriveInterval([7, 9])).toBeNull() // equal gap, but half the day unused
    expect(deriveInterval([0, 6, 12])).toBeNull() // three into 24 is 8, not 6
    expect(deriveInterval([1, 5, 9])).toBeNull()
  })

  it('has no opinion about a single time or none at all', () => {
    expect(deriveInterval([9])).toBeNull()
    expect(deriveInterval([])).toBeNull()
  })

  it('round-trips every interval it offers', () => {
    for (const every of INTERVAL_CHOICES) {
      expect(deriveInterval(hoursForInterval(every, 0))).toBe(every)
    }
  })
})

describe('local/UTC hours', () => {
  const NEW_YORK_EDT = 240 // UTC-4, in getTimezoneOffset's sign convention
  const BERLIN_CEST = -120 // UTC+2
  const KOLKATA = -330 // UTC+5:30

  it('converts both ways in a whole-hour zone', () => {
    expect(localHourToUtcHour(7, NEW_YORK_EDT)).toBe(11)
    expect(utcHourToLocalHour(11, NEW_YORK_EDT)).toBe(7)
    expect(localHourToUtcHour(7, BERLIN_CEST)).toBe(5)
    expect(utcHourToLocalHour(5, BERLIN_CEST)).toBe(7)
  })

  it('wraps around midnight in both directions', () => {
    expect(localHourToUtcHour(22, NEW_YORK_EDT)).toBe(2)
    expect(utcHourToLocalHour(2, NEW_YORK_EDT)).toBe(22)
    expect(localHourToUtcHour(0, BERLIN_CEST)).toBe(22)
    expect(utcHourToLocalHour(22, BERLIN_CEST)).toBe(0)
  })

  it('rounds a half-hour zone to the nearest hour, and says so by staying stable', () => {
    // Kolkata is UTC+5:30, so 07:00 local is 01:30 UTC and no stored hour is
    // exact: hour 2 reads back as 07:30, hour 1 as 06:30. Either is half an
    // hour out. What it must NOT do is drift further on every save — pick and
    // unpick the same time and it stays where it was put.
    const stored = localHourToUtcHour(7, KOLKATA)
    expect(stored).toBe(2)
    expect(localHourToUtcHour(utcHourToLocalHour(stored, KOLKATA), KOLKATA)).toBe(stored)
  })
})
