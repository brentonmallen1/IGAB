import { describe, expect, it } from 'vitest'
import { getTargetTooltip, ordinal } from './targetTooltip'

const money = (n: number) => `$${n.toFixed(2)}`

describe('ordinal', () => {
  it('handles the teens and the ones', () => {
    expect([1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 28].map(ordinal)).toEqual([
      '1st',
      '2nd',
      '3rd',
      '4th',
      '11th',
      '12th',
      '13th',
      '21st',
      '22nd',
      '23rd',
      '28th',
    ])
  })
})

describe('getTargetTooltip', () => {
  it('funded says so whatever the figures', () => {
    expect(getTargetTooltip('funded', 50, money)).toBe('Funded')
  })
  it('underfunded names the month ask', () => {
    expect(getTargetTooltip('underfunded', 50, money)).toBe('Need $50.00 this month')
    expect(getTargetTooltip('underfunded', 0, money)).toBe('Underfunded')
  })
  it('pending says when it will be checked', () => {
    expect(getTargetTooltip('pending', 50, money, 15)).toBe(
      'Pending: $50.00 still to assign — checked after the 15th'
    )
    expect(getTargetTooltip('pending', undefined, money)).toBe('Pending')
  })
})
