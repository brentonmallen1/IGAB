import { describe, expect, it } from 'vitest'
import { necessityReading, sheddableShare } from './necessityView'

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

describe('sheddableShare', () => {
  it('is the gap as a share of what is committed', () => {
    // Cost of living 1,800 with 400 of it non-essential.
    expect(sheddableShare(1800, 400)).toBeCloseTo(22.22, 2)
  })

  it('is unknown rather than zero when nothing is committed', () => {
    expect(sheddableShare(0, 0)).toBeNull()
    expect(sheddableShare(-5, 0)).toBeNull()
  })

  it('reads 100 when none of it is essential', () => {
    expect(sheddableShare(500, 500)).toBe(100)
  })

  it('is unknown when the gap is — nothing tagged Essential', () => {
    expect(sheddableShare(1800, null)).toBeNull()
  })
})
