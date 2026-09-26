import { describe, expect, it } from 'vitest'
import { deltaTone } from './metricDelta'

describe('deltaTone', () => {
  it('reads spending up as bad news, and down as good', () => {
    // "Spent +21%" was coloured green: the card coloured by sign.
    expect(deltaTone(21, 'down')).toBe('bad')
    expect(deltaTone(-12, 'down')).toBe('good')
  })

  it('reads net worth up as good news, and down as bad', () => {
    expect(deltaTone(10, 'up')).toBe('good')
    expect(deltaTone(-10, 'up')).toBe('bad')
  })

  it('reads any change of a neutral figure as neither', () => {
    expect(deltaTone(40, 'neutral')).toBe('neutral')
    expect(deltaTone(-40, 'neutral')).toBe('neutral')
  })

  it('reads no change, or one that prints as 0.0%, as neither', () => {
    expect(deltaTone(0, 'down')).toBe('neutral')
    expect(deltaTone(0.04, 'down')).toBe('neutral')
    expect(deltaTone(-0.04, 'up')).toBe('neutral')
    expect(deltaTone(0.06, 'down')).toBe('bad')
    expect(deltaTone(-0.06, 'down')).toBe('good')
  })
})
