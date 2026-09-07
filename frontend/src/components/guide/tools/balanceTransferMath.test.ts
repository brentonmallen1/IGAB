import { describe, expect, it } from 'vitest'
import { compareTransfer } from './balanceTransferMath'

describe('compareTransfer', () => {
  it('a 0% promo long enough to clear the balance saves the interest minus the fee', () => {
    // $2,400 at 24% paid at $200/mo stays ~14 months with a few hundred in
    // interest; transferred at 3% ($72 fee) on 0% for 18 months it clears in
    // 13 with none.
    const r = compareTransfer({
      balance: 2400,
      currentApr: 24,
      payment: 200,
      feePercent: 3,
      promoMonths: 18,
      promoApr: 0,
      postPromoApr: 27,
    })
    expect(r.stay.months).toBe(14)
    expect(r.stay.interest).toBeGreaterThan(300)
    expect(r.transfer.fee).toBe(72)
    expect(r.transfer.months).toBe(13)
    expect(r.transfer.interest).toBe(0)
    expect(r.saving).toBeCloseTo(r.stay.interest - 72, 2)
  })

  it('a promo too short leaves a balance charged at the new rate', () => {
    const r = compareTransfer({
      balance: 2400,
      currentApr: 24,
      payment: 200,
      feePercent: 3,
      promoMonths: 6,
      promoApr: 0,
      postPromoApr: 27,
    })
    expect(r.transfer.balanceAtPromoEnd).toBeCloseTo(2472 - 1200, 2)
    expect(r.transfer.interest).toBeGreaterThan(0)
  })

  it('a payment under the interest never pays off, and says so', () => {
    const r = compareTransfer({
      balance: 10000,
      currentApr: 24,
      payment: 100,
      feePercent: 3,
      promoMonths: 12,
      promoApr: 0,
      postPromoApr: 24,
    })
    expect(r.stay.months).toBeNull()
    expect(r.transfer.months).toBeNull()
  })
})
