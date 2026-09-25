import { describe, expect, it } from 'vitest'
import { overspentAfterPayment, thisMonthOrNext } from './cardOverspending'

describe('overspentAfterPayment', () => {
  it('is null for a payment Set aside covers', () => {
    expect(overspentAfterPayment(500, 500)).toBeNull()
    expect(overspentAfterPayment(500, 200)).toBeNull()
  })

  it('is what the payment runs past Set aside', () => {
    expect(overspentAfterPayment(500, 650)).toBe(150)
  })

  it('counts a card that is already below zero', () => {
    // Already 50 overspent; paying 100 more leaves 150 to cover, not 100.
    expect(overspentAfterPayment(-50, 100)).toBe(150)
  })

  it('works in cents, so float residue never reads as overspending', () => {
    expect(overspentAfterPayment(0.3, 0.1 + 0.2)).toBeNull()
  })
})

describe('thisMonthOrNext', () => {
  it('names the amount and both outcomes', () => {
    expect(thisMonthOrNext('$150.00')).toBe(
      'Assign $150.00 to the card this month, or it comes out of next month’s Ready to Assign.'
    )
  })
})
