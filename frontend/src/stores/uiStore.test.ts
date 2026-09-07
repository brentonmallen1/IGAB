import { describe, expect, it } from 'vitest'
import { ALL_QUICK_FILTERS, mergeQuickFilterOrder, normalizeBudgetRowMode } from './uiStore'

describe('mergeQuickFilterOrder', () => {
  it('a persisted order without pending gains it', () => {
    // Every existing user has an order saved from before the chip existed;
    // without this the new chip would never appear for them.
    expect(
      mergeQuickFilterOrder(['overfunded', 'overspent', 'underfunded', 'money-available'])
    ).toEqual(['overfunded', 'overspent', 'underfunded', 'money-available', 'pending'])
  })

  it('keeps a complete saved order as it is', () => {
    const saved = [...ALL_QUICK_FILTERS].reverse()
    expect(mergeQuickFilterOrder(saved)).toEqual(saved)
  })

  it('drops a filter that no longer exists and starts from the canonical order when nothing was saved', () => {
    expect(mergeQuickFilterOrder(['overspent', 'retired'])).toEqual([
      'overspent',
      'underfunded',
      'pending',
      'money-available',
      'overfunded',
    ])
    expect(mergeQuickFilterOrder(undefined)).toEqual(ALL_QUICK_FILTERS)
  })
})

describe('normalizeBudgetRowMode', () => {
  it("reads a persisted 'compressed' as dense — that is what it meant", () => {
    expect(normalizeBudgetRowMode('compressed')).toBe('dense')
  })
  it('keeps the two new modes and falls back to expanded', () => {
    expect(normalizeBudgetRowMode('compact')).toBe('compact')
    expect(normalizeBudgetRowMode('dense')).toBe('dense')
    expect(normalizeBudgetRowMode(undefined)).toBe('expanded')
    expect(normalizeBudgetRowMode('bogus')).toBe('expanded')
  })
})
