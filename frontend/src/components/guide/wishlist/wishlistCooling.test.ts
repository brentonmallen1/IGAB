/**
 * The form's preview of a cooling-off in days. `shared/cooling_cases.json` is
 * the same table the backend's `cooling_until_for` runs, so the date the form
 * shows while typing is the date the server saves.
 */
import { describe, expect, it } from 'vitest'
import cooling from '../../../../../shared/cooling_cases.json'
import {
  coolingUntilFromDays,
  daysAfterAdded,
  parseCoolingDays,
  parseDays,
} from './wishlistCooling'

describe('shared cooling cases', () => {
  it.each(cooling.cases)('$note: days → date', ({ added_on, days, cooling_until }) => {
    expect(coolingUntilFromDays(added_on, days)).toBe(cooling_until)
  })

  it.each(cooling.cases)('$note: date → days', ({ added_on, days, cooling_until }) => {
    expect(daysAfterAdded(added_on, cooling_until)).toBe(days)
  })
})

describe('coolingUntilFromDays', () => {
  it('clamps negative days to the day added, as the server does', () => {
    expect(coolingUntilFromDays('2026-08-01', -3)).toBe('2026-08-01')
  })
})

describe('daysAfterAdded', () => {
  it('is negative for a date before the wish was added', () => {
    expect(daysAfterAdded('2026-08-10', '2026-08-07')).toBe(-3)
  })
})

describe('parseCoolingDays', () => {
  it('reads blank as no figure', () => {
    expect(parseCoolingDays('', 365)).toEqual({ ok: true, days: null })
    expect(parseCoolingDays('   ', 365)).toEqual({ ok: true, days: null })
  })

  it('accepts 0 and the limit itself', () => {
    expect(parseCoolingDays('0', 365)).toEqual({ ok: true, days: 0 })
    expect(parseCoolingDays(' 365 ', 365)).toEqual({ ok: true, days: 365 })
  })

  it.each(['366', '-1', '1.5', '14 days', 'abc', '1e2'])(
    'refuses %s rather than reading it as a number it is not',
    (text) => {
      const parsed = parseCoolingDays(text, 365)
      expect(parsed.ok).toBe(false)
      if (!parsed.ok) expect(parsed.error).toMatch(/0 to 365/)
    }
  )

  it('states the served limit, not a spelled one', () => {
    const parsed = parseCoolingDays('100', 90)
    expect(parsed).toEqual({
      ok: false,
      error: 'Cooling-off days must be a whole number from 0 to 90',
    })
  })
})

describe('parseDays', () => {
  const settings = { min: 7, max: 365, label: 'Review days', blank: 'refuse' } as const

  it('refuses a blank where a number is required, rather than reading it as 0', () => {
    // `Number('')` is 0. The settings dialog did exactly that, so clearing
    // the cooling-off box silently set a zero-day one on every future wish.
    const r = parseDays('', settings)
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toContain('7 to 365')
  })

  it('refuses below the served minimum', () => {
    expect(parseDays('3', settings).ok).toBe(false)
  })

  it('refuses above the served maximum', () => {
    expect(parseDays('400', settings).ok).toBe(false)
  })

  it('refuses what is not a whole number', () => {
    expect(parseDays('9.5', settings).ok).toBe(false)
    expect(parseDays('soon', settings).ok).toBe(false)
  })

  it('takes a whole number inside the range', () => {
    expect(parseDays('30', settings)).toEqual({ ok: true, days: 30 })
  })

  it('names the field it is refusing, since two of them share this', () => {
    const r = parseDays('x', settings)
    if (!r.ok) expect(r.error).toContain('Review days')
  })

  it('still lets a wish have no cooling-off at all', () => {
    // The one genuine difference between the two callers, expressed as a
    // parameter rather than a second copy.
    expect(parseDays('', { max: 365, label: 'Cooling-off days', blank: 'null' })).toEqual({
      ok: true,
      days: null,
    })
  })
})
