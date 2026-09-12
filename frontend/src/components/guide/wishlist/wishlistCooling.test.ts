/**
 * The form's preview of a cooling-off in days. `shared/cooling_cases.json` is
 * the same table the backend's `cooling_until_for` runs, so the date the form
 * shows while typing is the date the server saves.
 */
import { describe, expect, it } from 'vitest'
import cooling from '../../../../../shared/cooling_cases.json'
import { coolingUntilFromDays, daysAfterAdded, parseCoolingDays } from './wishlistCooling'

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
