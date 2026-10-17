/**
 * The one spelling of owed / covered. Each case names the surface that used to
 * carry its own copy, because those copies are what this replaced.
 */
import { describe, expect, it } from 'vitest'
import { cardCoverage } from './cardCoverage'

describe('cardCoverage', () => {
  it('a part-funded card: owes 1,200, 300 set aside covers a quarter', () => {
    expect(cardCoverage({ balance: -1200, set_aside: 300 })).toEqual({
      owed: 1200,
      covered: 300,
      share: 0.25,
    })
  })

  it('caps covered at what is owed — the payment dialog once proposed paying the whole envelope', () => {
    // The over-reserved card: 1,250 set aside against a 50 bill. Covered is
    // the bill, not the envelope, so the prefill offers 50.
    expect(cardCoverage({ balance: -50, set_aside: 1250 })).toEqual({
      owed: 50,
      covered: 50,
      share: 1,
    })
  })

  it('an overspent card covers nothing: a negative Set aside is not negative cover', () => {
    expect(cardCoverage({ balance: -400, set_aside: -100 })).toEqual({
      owed: 400,
      covered: 0,
      share: 0,
    })
  })

  it('a card that owes nothing reads fully covered — the bar is full, not empty', () => {
    expect(cardCoverage({ balance: 0, set_aside: 0 })).toEqual({ owed: 0, covered: 0, share: 1 })
  })

  it('a card holding your money owes nothing, whatever it reserves', () => {
    expect(cardCoverage({ balance: 75, set_aside: 20 })).toEqual({ owed: 0, covered: 0, share: 1 })
  })
})
