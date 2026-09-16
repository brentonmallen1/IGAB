import { describe, expect, it } from 'vitest'
import type { EssentialsFigures } from '../types'
import { otherFigureNote } from './essentialsFigures'

const money = (n: number) =>
  `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

const figures = (over: Partial<EssentialsFigures> = {}): EssentialsFigures => ({
  as_paid: 2530,
  spread: 2140,
  spread_on: true,
  monthly: 2140,
  ...over,
})

describe('otherFigureNote', () => {
  it('leads with the spread figure when the setting is on', () => {
    expect(otherFigureNote(figures(), money)).toBe('$2,140.00/mo spread · $2,530.00/mo as paid')
  })

  it('leads with the as-paid figure when the setting is off', () => {
    expect(otherFigureNote(figures({ spread_on: false, monthly: 2530 }), money)).toBe(
      '$2,530.00/mo as paid · $2,140.00/mo spread'
    )
  })

  it('says nothing when the two agree', () => {
    expect(otherFigureNote(figures({ as_paid: 2140 }), money)).toBeNull()
    expect(otherFigureNote(figures({ as_paid: 0, spread: 0, monthly: 0 }), money)).toBeNull()
  })

  it('says nothing without figures', () => {
    expect(otherFigureNote(null, money)).toBeNull()
    expect(otherFigureNote(undefined, money)).toBeNull()
  })
})
