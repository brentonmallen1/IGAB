import { describe, expect, it } from 'vitest'
import { addDaysISO, daysBetween, monthWindow, previousWindow } from './dateWindow'
import { toISODate } from './dates'
import { pinTimeZone } from '../test-utils/timeZone'

describe('addDaysISO', () => {
  it('adds within a month', () => {
    expect(addDaysISO('2026-07-10', 5)).toBe('2026-07-15')
  })
  it('crosses month boundaries', () => {
    expect(addDaysISO('2026-07-31', 1)).toBe('2026-08-01')
    expect(addDaysISO('2026-08-01', -1)).toBe('2026-07-31')
  })
  it('crosses year boundaries', () => {
    expect(addDaysISO('2026-01-01', -1)).toBe('2025-12-31')
  })
  it('handles leap February', () => {
    expect(addDaysISO('2024-02-28', 1)).toBe('2024-02-29')
    expect(addDaysISO('2025-02-28', 1)).toBe('2025-03-01')
  })
})

describe('daysBetween', () => {
  it('same day is zero', () => {
    expect(daysBetween('2026-07-21', '2026-07-21')).toBe(0)
  })
  it('spans months', () => {
    expect(daysBetween('2026-05-01', '2026-07-21')).toBe(81)
  })
})

describe('previousWindow', () => {
  it('returns the equal-length window immediately before', () => {
    // May 1 – Jul 21 is 82 days inclusive → Feb 8 – Apr 30
    expect(previousWindow('2026-05-01', '2026-07-21')).toEqual({
      start: '2026-02-08',
      end: '2026-04-30',
    })
  })
  it('single-day window maps to the previous day', () => {
    expect(previousWindow('2026-07-21', '2026-07-21')).toEqual({
      start: '2026-07-20',
      end: '2026-07-20',
    })
  })
  it('crosses a year boundary', () => {
    expect(previousWindow('2026-01-01', '2026-01-31')).toEqual({
      start: '2025-12-01',
      end: '2025-12-31',
    })
  })
  it('handles leap February', () => {
    expect(previousWindow('2024-03-01', '2024-03-29')).toEqual({
      start: '2024-02-01',
      end: '2024-02-29',
    })
  })
})

describe('monthWindow', () => {
  it('covers a full past month', () => {
    expect(monthWindow('2026-02')).toEqual({ start: '2026-02-01', end: '2026-02-28' })
  })
  it('covers leap February', () => {
    expect(monthWindow('2024-02')).toEqual({ start: '2024-02-01', end: '2024-02-29' })
  })
  it('clamps the current month to today', () => {
    const now = new Date()
    const ym = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
    const dd = String(now.getDate()).padStart(2, '0')
    expect(monthWindow(ym).end).toBe(`${ym}-${dd}`)
  })
})

/**
 * `toISODate` replaced `d.toISOString().slice(0, 10)` in DateRangePicker and in
 * reportStore.defaultFilters. That round-trip converts to UTC first, so a
 * LOCAL midnight ahead of Greenwich lands on the previous calendar day — which
 * made "This month" ask the server for a window starting on the last day of
 * the month before. Behind Greenwich the same round-trip pushes an afternoon
 * "today" onto tomorrow.
 *
 * Both blocks pin a zone, because in UTC the broken and the fixed versions
 * agree and the test would prove nothing.
 */
describe('toISODate ahead of Greenwich', () => {
  pinTimeZone('Europe/Berlin')

  it('keeps a local month-start on the 1st', () => {
    // toISOString() gave '2026-08-31' for this Date.
    expect(toISODate(new Date(2026, 8, 1))).toBe('2026-09-01')
  })

  it('keeps a local month-end on its last day', () => {
    expect(toISODate(new Date(2026, 8, 30))).toBe('2026-09-30')
  })
})

describe('toISODate behind Greenwich', () => {
  pinTimeZone('America/Los_Angeles')

  it('does not push an afternoon today onto tomorrow', () => {
    // 18:00 PDT on 30 Sep is 01:00 UTC on 1 Oct; toISOString() said October.
    expect(toISODate(new Date(2026, 8, 30, 18, 0))).toBe('2026-09-30')
  })
})
