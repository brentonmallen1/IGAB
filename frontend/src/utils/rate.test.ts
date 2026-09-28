import { describe, expect, it } from 'vitest'
import { formatRate } from './rate'

describe('formatRate', () => {
  it('drops trailing zeros and keeps up to three places', () => {
    expect(formatRate(6.5)).toBe('6.5%')
    expect(formatRate(24.99)).toBe('24.99%')
    expect(formatRate(6.125)).toBe('6.125%')
    expect(formatRate(7)).toBe('7%')
  })

  it('zero is a real rate — a promo card has one', () => {
    expect(formatRate(0)).toBe('0%')
  })

  it('rounds a stored fourth place', () => {
    expect(formatRate(6.4999)).toBe('6.5%')
  })
})
