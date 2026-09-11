import { describe, expect, it } from 'vitest'
import { averagedOver } from './averagedOver'

describe('averagedOver', () => {
  it('names the months the average divides by', () => {
    expect(averagedOver('per month', 11)).toBe('per month, over 11 complete months')
  })

  it('says one month, not one months', () => {
    expect(averagedOver('effective', 1)).toBe('effective, over 1 complete month')
  })

  it('says a young budget has no complete month yet as a count', () => {
    expect(averagedOver('per month', 0)).toBe('per month, over 0 complete months')
  })
})
