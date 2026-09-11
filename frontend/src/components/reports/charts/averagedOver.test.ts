import { describe, expect, it } from 'vitest'
import { averagedOver, averagedSinceEachFirstCharge } from './averagedOver'

describe('averagedOver', () => {
  it('names the months the average divides by', () => {
    expect(averagedOver('per month', 11)).toBe('per month, over 11 complete months')
  })

  it('says one month, not one months', () => {
    expect(averagedOver('per month', 1)).toBe('per month, over 1 complete month')
  })

  it('says a young budget has no complete month yet as a count', () => {
    expect(averagedOver('per month', 0)).toBe('per month, over 0 complete months')
  })
})

describe('averagedSinceEachFirstCharge', () => {
  // Subscriptions' headline is not one average over one window: every service
  // divides by the complete months since ITS first charge, and the category
  // and summary figures are those lines added up. "effective, over 11
  // complete months" named a divisor nothing on the page used.
  it('says each service is averaged since its own first charge', () => {
    expect(averagedSinceEachFirstCharge(11)).toBe(
      'effective, each service since its first charge, at most 11 complete months'
    )
  })

  it('bounds the count instead of claiming it as the divisor', () => {
    expect(averagedSinceEachFirstCharge(11)).toContain('at most')
    expect(averagedSinceEachFirstCharge(11)).not.toContain('over 11')
  })

  it('says one month, not one months, like the card beside it', () => {
    expect(averagedSinceEachFirstCharge(1)).toBe(
      'effective, each service since its first charge, at most 1 complete month'
    )
  })
})
