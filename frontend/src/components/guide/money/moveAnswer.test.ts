import { describe, expect, it } from 'vitest'
import { explanation, ZERO_FIGURES } from '../../../test-utils/moneyRulesFixtures'
import { heldLine, savedParts } from './moveAnswer'

const money = (n: number) => `$${n.toFixed(2)}`

describe('heldLine', () => {
  it('says what a kept-here envelope comes to hold, signed', () => {
    expect(heldLine(explanation({ held: -300 }), money)).toBe('Held in the envelope: −$300.00')
    expect(heldLine(explanation({ held: 40 }), money)).toBe('Held in the envelope: +$40.00')
  })

  it('is absent when the move holds nothing', () => {
    expect(heldLine(explanation({ held: 0 }), money)).toBeNull()
  })
})

describe('savedParts', () => {
  it('splits saved into moved and held when anything was held', () => {
    const figures = { ...ZERO_FIGURES, savings: -120, savings_moved: 300, savings_held: -420 }
    expect(savedParts(figures, money)).toBe('moved $300.00 + held −$420.00')
  })

  it('leaves saved alone when it is the moved figure', () => {
    const figures = { ...ZERO_FIGURES, savings: 750, savings_moved: 750, savings_held: 0 }
    expect(savedParts(figures, money)).toBeNull()
  })
})
