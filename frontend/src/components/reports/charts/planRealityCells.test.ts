import { describe, expect, it } from 'vitest'
import { cellLabel, isActive, overspendStyle } from './planRealityCells'
import { PRIVACY_MASK } from '../../../utils/money'

describe('cellLabel', () => {
  it('signs the variance and abbreviates it', () => {
    expect(cellLabel(-40, false)).toBe('−40')
    expect(cellLabel(10, false)).toBe('+10')
    expect(cellLabel(4180, false)).toBe('+4.2k')
    expect(cellLabel(0, false)).toBe('0')
  })

  it('is the mask alone in privacy mode, sign and zero included', () => {
    // It put the sign outside the mask — "−••••" over plan, "+••••" under —
    // and printed an on-plan month as a literal "0", so the overspend could
    // be read straight off the grid.
    for (const v of [-40, 10, 0, -4180]) expect(cellLabel(v, true)).toBe(PRIVACY_MASK)
  })
})

describe('overspendStyle', () => {
  it('tints only an overspent month, deeper for the worst one on screen', () => {
    expect(overspendStyle(10, 40)).toEqual({})
    expect(overspendStyle(0, 40)).toEqual({})
    expect(overspendStyle(-40, 40).background).toContain('38%')
    expect(overspendStyle(-20, 40).background).toContain('23%')
  })
})

describe('isActive', () => {
  it('is active when either the plan or the spending is non-zero', () => {
    expect(isActive({ month: '2026-06-01', assigned: 0, spent: 0, variance: 0 })).toBe(false)
    expect(isActive({ month: '2026-06-01', assigned: 900, spent: 900, variance: 0 })).toBe(true)
    expect(isActive({ month: '2026-06-01', assigned: 0, spent: 12, variance: -12 })).toBe(true)
  })
})
