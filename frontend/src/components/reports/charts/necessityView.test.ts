import { describe, expect, it } from 'vitest'
import {
  necessityReading,
  necessityShare,
  nonEssentialSpend,
  takeHomeLine,
  takeHomeSplit,
  tiersAreEqual,
} from './necessityView'

describe('necessityReading', () => {
  it('says nothing rather than guessing when there is no income', () => {
    const r = necessityReading(null, null)
    expect(r.standing).toBe('unknown')
    expect(r.underwater).toBe(false)
    expect(r.note).toMatch(/no income/i)
  })

  it('reads a household with room as comfortable', () => {
    expect(necessityReading(42, 30).standing).toBe('comfortable')
    // Exactly half belongs to the better band, and the copy has to be true
    // there: "under half" would be wrong at the boundary.
    expect(necessityReading(50, 38).note).toMatch(/no more than half/i)
  })

  it('bands the middle against the rule of thumb it cites', () => {
    expect(necessityReading(50, 40).standing).toBe('comfortable')
    expect(necessityReading(50.1, 40).standing).toBe('workable')
    expect(necessityReading(70, 40).standing).toBe('workable')
    expect(necessityReading(70.1, 40).standing).toBe('tight')
    expect(necessityReading(90, 40).standing).toBe('tight')
    expect(necessityReading(90.1, 40).standing).toBe('no-headroom')
  })

  it('calls essentials outrunning take-home what it is, not merely tight', () => {
    // Cost of living 120% and essentials 105%: the wide ratio alone would
    // say "no headroom", which understates a household that cannot cover
    // even the things it could not cut.
    const r = necessityReading(120, 105)
    expect(r.underwater).toBe(true)
    expect(r.standing).toBe('no-headroom')
    expect(r.note).toMatch(/could not cut/i)
  })

  it('does not call a household underwater on the wide ratio alone', () => {
    const r = necessityReading(95, 60)
    expect(r.underwater).toBe(false)
    expect(r.standing).toBe('no-headroom')
  })
})

describe('nonEssentialSpend', () => {
  it('is the wide tier less the lean one', () => {
    // Cost of living 1,800 with 1,400 of it essential.
    expect(nonEssentialSpend(1800, 1400)).toBe(400)
  })

  it('is unknown, not zero, until something is tagged Essential', () => {
    // The lean tier unchosen is not "nothing could be cut".
    expect(nonEssentialSpend(1800, null)).toBeNull()
  })

  it('floors at zero when a refund puts the wide tier under the lean one', () => {
    // The wide tier contains the lean one, but its tag arms net refunds: a
    // refund filed to a Cost-of-living category can invert them, and nobody
    // committed to -$40.
    expect(nonEssentialSpend(1360, 1400)).toBe(0)
  })
})

describe('necessityShare', () => {
  it('divides the two figures the cards beside it print', () => {
    // Required: $1,800 committed out of $3,600 taken home is the 50% the page
    // shows, checkable on paper from the two cards.
    expect(necessityShare(1800, 3600)).toBe(50)
    // The essentials ratio, same take-home: 1,400 of 3,600.
    expect(necessityShare(1400, 3600)).toBeCloseTo(38.89, 2)
    // And the sheddable share, which divides the gap by the wide tier.
    expect(necessityShare(400, 1800)).toBeCloseTo(22.22, 2)
  })

  it('is unknown rather than 100 when there is no income on record', () => {
    expect(necessityShare(1800, 0)).toBeNull()
    expect(necessityShare(0, 0)).toBeNull()
    // A window whose refunds beat its income has no positive whole either.
    expect(necessityShare(1800, -5)).toBeNull()
  })

  it('is unknown when the part is — nothing tagged Essential', () => {
    expect(necessityShare(null, 3600)).toBeNull()
  })

  it('reads 100 when the part is the whole of it', () => {
    expect(necessityShare(500, 500)).toBe(100)
  })
})

describe('tiersAreEqual', () => {
  it('is true when everything committed is Essential, to the cent', () => {
    expect(tiersAreEqual(1800, 1800)).toBe(true)
    expect(tiersAreEqual(1800, 1799.99)).toBe(false)
  })

  it('is false while nothing is tagged Essential', () => {
    expect(tiersAreEqual(1800, null)).toBe(false)
  })
})

describe('takeHomeSplit', () => {
  const money = (n: number) => `$${n.toFixed(2)}`

  it('lays take-home out as committed, discretionary and left over', () => {
    const split = takeHomeSplit(5000, 3000, 1200)
    expect(split).toEqual({
      committed: 3000,
      discretionary: 1200,
      leftOver: 800,
      committedPct: 60,
      discretionaryPct: 24,
      leftOverPct: 16,
    })
    expect(takeHomeLine(5000, split!, money)).toBe(
      'Of $5000.00 take-home a month: $3000.00 committed (60%) · $1200.00 discretionary (24%) · $800.00 left over (16%)'
    )
  })

  it('says a shortfall as one, not as a negative left over', () => {
    const split = takeHomeSplit(3000, 2800, 500)!
    expect(split.leftOver).toBe(-300)
    expect(takeHomeLine(3000, split, money)).toMatch(/\$300\.00 more than came in \(-10%\)$/)
  })

  it('prints percentages that add to 100 when each rounds', () => {
    // 1/3 each: 33 + 33 + 34.
    const split = takeHomeSplit(3, 1, 1)!
    expect(split.committedPct + split.discretionaryPct + split.leftOverPct).toBe(100)
  })

  it('is unknown with no take-home or no discretionary figure', () => {
    expect(takeHomeSplit(0, 100, 50)).toBeNull()
    expect(takeHomeSplit(-10, 100, 50)).toBeNull()
    expect(takeHomeSplit(5000, 3000, null)).toBeNull()
  })
})
