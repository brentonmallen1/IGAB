import { describe, expect, it } from 'vitest'
import { addDaysISO, daysBetween, monthWindow, previousWindow } from './dateWindow'

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
