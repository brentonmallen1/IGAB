import { describe, expect, it } from 'vitest'
import { compactMoney, MONEY_AXIS_WIDTH } from './moneyAxis'

describe('compactMoney', () => {
  it.each([
    [0, '$0'],
    [800, '$800'],
    [999.6, '$1000'],
    [1200, '$1.2k'],
    [1250, '$1.3k'],
    // Adjacent gridlines stay distinct: the hand-rolled `Math.round(v / 1000)`
    // called both of these "$2k".
    [1500, '$1.5k'],
    [2400, '$2.4k'],
    [9950, '$10k'],
    [12345.67, '$12k'],
    [1_500_000, '$1.5M'],
    // The hand-rolled copy counted thousands forever: "$2400k".
    [2_400_000, '$2.4M'],
    [2_400_000_000, '$2.4B'],
    [-1200, '-$1.2k'],
    [-45, '-$45'],
  ])('%s → %s', (amount, expected) => {
    expect(compactMoney(amount, '$')).toBe(expected)
  })

  it('uses the budget currency symbol', () => {
    expect(compactMoney(1200, '€')).toBe('€1.2k')
  })
})

describe('MONEY_AXIS_WIDTH', () => {
  it('gives a phone the axis it needs and no more', () => {
    expect(MONEY_AXIS_WIDTH.phone).toBeLessThan(MONEY_AXIS_WIDTH.desktop)
    expect(MONEY_AXIS_WIDTH.phone).toBeGreaterThanOrEqual(48)
  })
})
