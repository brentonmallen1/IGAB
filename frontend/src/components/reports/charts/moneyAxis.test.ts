import { describe, expect, it } from 'vitest'
import { compactMoney, MONEY_AXIS_WIDTH } from './moneyAxis'

describe('compactMoney', () => {
  it.each([
    [0, '$0'],
    [800, '$800'],
    [999.6, '$1000'],
    [1200, '$1.2k'],
    [1250, '$1.3k'],
    [9950, '$10k'],
    [12345.67, '$12k'],
    [1_500_000, '$1.5M'],
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

/**
 * Five report charts carried their own axis formatter:
 *
 *   Math.abs(v) >= 1000 ? `${sym}${Math.round(v / 1000)}k` : `${sym}${Math.round(v)}`
 *
 * `Math.round(v / 1000)` is the defect — it collapses a whole band of values
 * onto one label, so two different gridlines on the same axis both read "$2k".
 * Two more charts printed `${sym}${v}` with no rounding at all, drawing ticks
 * like "$1234.5600000001". All seven now spread `useMoneyAxis`.
 */
describe('the axis label the five hand-rolled copies got wrong', () => {
  const kRound = (v: number, symbol: string) =>
    Math.abs(v) >= 1000 ? `${symbol}${Math.round(v / 1000)}k` : `${symbol}${Math.round(v)}`

  it('gives adjacent gridlines distinct labels', () => {
    // The old copy called both of these "$2k".
    expect(kRound(1500, '$')).toBe(kRound(2400, '$'))
    expect(compactMoney(1500, '$')).not.toBe(compactMoney(2400, '$'))
    expect(compactMoney(1500, '$')).toBe('$1.5k')
    expect(compactMoney(2400, '$')).toBe('$2.4k')
  })

  it('scales past a million instead of counting thousands forever', () => {
    // The old copy rendered 2.4M as "$2400k".
    expect(kRound(2_400_000, '$')).toBe('$2400k')
    expect(compactMoney(2_400_000, '$')).toBe('$2.4M')
  })

  it('honours the budget currency symbol it is given', () => {
    expect(compactMoney(1500, '€')).toBe('€1.5k')
  })
})
