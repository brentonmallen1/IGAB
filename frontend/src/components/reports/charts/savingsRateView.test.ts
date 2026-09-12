/**
 * The Savings Rate tooltip's two fixes — the rate as a percentage, and one
 * formatter for the rate — lived in a module-private function nothing
 * tested. Simplifying the chart to `formatter={formatMoney}` passed tsc,
 * eslint and every test while the rate 18.5 rendered as "$18.50" again.
 */
import { renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { pct, RATE_SERIES, savingsRateTooltipWith } from './savingsRateView'
import { useFormatters } from '../../../hooks/useFormatters'
import { useAppStore } from '../../../stores/appStore'

const money = (n: number) => `$${n.toFixed(2)}`

afterEach(() => {
  useAppStore.setState({ privacyMode: false })
})

describe('pct', () => {
  it('prints a negative rate rather than flooring it at 0%', () => {
    // The Overview's card clamped with its own formatter and read 0.0% where
    // the tab read -40.0% for the same served rate.
    expect(pct(-0.4)).toBe('-40.0%')
    expect(pct(0.25)).toBe('25.0%')
  })

  it('has no rate without income', () => {
    expect(pct(null)).toBe('—')
  })
})

describe('savingsRateTooltipWith', () => {
  it('reads the rate line as a percentage', () => {
    expect(savingsRateTooltipWith(money)(18.5, RATE_SERIES)).toBe('18.5%')
  })

  it('routes every bar series to the money formatter', () => {
    const fmt = savingsRateTooltipWith(money)
    expect(fmt(900, 'Saved')).toBe('$900.00')
    expect(fmt(120, 'Debt Paid')).toBe('$120.00')
    expect(fmt(3100, 'Spent')).toBe('$3100.00')
  })

  it('says the rate exactly as the metric card does', () => {
    // The tooltip had its own `${value.toFixed(1)}%` beside the card's pct.
    // The line plots the rate ×100; the card is handed the fraction.
    for (const rate of [0.185, 0.2, 0.0625, -0.4, 1]) {
      expect(savingsRateTooltipWith(money)(rate * 100, RATE_SERIES)).toBe(pct(rate))
    }
  })

  it('masks the money bars in privacy mode', () => {
    useAppStore.setState({ privacyMode: true })
    const { formatMoney } = renderHook(() => useFormatters()).result.current
    const fmt = savingsRateTooltipWith(formatMoney)
    expect(fmt(900, 'Saved')).toBe('$••••')
    expect(fmt(900, 'Saved')).not.toMatch(/\d/)
  })
})

describe('pct', () => {
  it('shows a dash for a month with no income, which has no rate', () => {
    expect(pct(null)).toBe('—')
    expect(pct(0)).toBe('0.0%')
  })
})
