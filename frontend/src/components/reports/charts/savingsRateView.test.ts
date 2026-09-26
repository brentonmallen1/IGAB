/**
 * The Savings Rate tooltip's two fixes — the rate as a percentage, and one
 * formatter for the rate — lived in a module-private function nothing
 * tested. Simplifying the chart to `formatter={formatMoney}` passed tsc,
 * eslint and every test while the rate 18.5 rendered as "$18.50" again.
 */
import { describe, expect, it } from 'vitest'
import { keptFigure, pct, rateTooltip } from './savingsRateView'

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

describe('rateTooltip', () => {
  it('reads the rate line as a percentage, never as money', () => {
    expect(rateTooltip(18.5)).toBe('18.5%')
  })

  it('says the rate exactly as the metric card does', () => {
    // The tooltip had its own `${value.toFixed(1)}%` beside the card's pct.
    // The line plots the rate ×100; the card is handed the fraction.
    for (const rate of [0.185, 0.2, 0.0625, -0.4, 1]) {
      expect(rateTooltip(rate * 100)).toBe(pct(rate))
    }
  })
})

describe('keptFigure', () => {
  const summary = { savings: 1000, debt_principal: 500 }

  it('is Saved alone for the plain rate', () => {
    expect(keptFigure(summary, false)).toBe(1000)
  })

  it('adds debt payments when the rate counts them', () => {
    // The card read "Saved $1,000" beside a 37.5% rate on $4,000 of income:
    // the rate counted the $500 of debt payments, the card did not.
    expect(keptFigure(summary, true)).toBe(1500)
    expect(keptFigure(summary, true) / 4000).toBe(0.375)
  })

  it('keeps a negative Saved negative, with or without debt', () => {
    expect(keptFigure({ savings: -1200, debt_principal: 800 }, false)).toBe(-1200)
    expect(keptFigure({ savings: -1200, debt_principal: 800 }, true)).toBe(-400)
  })

  it('is zero with nothing kept', () => {
    expect(keptFigure({ savings: 0, debt_principal: 0 }, true)).toBe(0)
  })
})

describe('pct', () => {
  it('shows a dash for a month with no income, which has no rate', () => {
    expect(pct(null)).toBe('—')
    expect(pct(0)).toBe('0.0%')
  })
})
