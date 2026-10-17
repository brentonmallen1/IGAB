import { describe, expect, it } from 'vitest'
import { chipInputValue, suggestionChips } from './targetSuggestions'
import type { TargetSuggestions } from '../../types'

const money = (n: number) => `$${n.toFixed(2)}`
const month = (m: string) => m.slice(0, 7)

function served(overrides: Partial<TargetSuggestions> = {}): TargetSuggestions {
  return {
    category_id: 'c1',
    average_spent: 210,
    peak_spent: 480,
    peak_spent_month: '2026-03-01',
    peak_available: 900,
    peak_available_month: '2026-06-01',
    months_counted: 12,
    ...overrides,
  }
}

const chips = (s: TargetSuggestions | undefined, type: string) =>
  suggestionChips(s, type, money, month).map((c) => [c.key, c.label, c.field])

describe('suggestionChips', () => {
  it('a monthly target is offered both spending figures and the balance as its stop', () => {
    expect(chips(served(), 'monthly_funding')).toEqual([
      ['average', 'Avg $210.00/mo', 'amount'],
      ['peak_spent', 'Peak month $480.00', 'amount'],
      ['peak_available', 'Peak balance $900.00', 'limit'],
    ])
  })

  it('a weekly target gets no monthly spending figure to misread as weekly', () => {
    expect(chips(served(), 'weekly_funding')).toEqual([
      ['peak_available', 'Peak balance $900.00', 'limit'],
    ])
  })

  it('a savings balance takes the peak month or the peak balance as the balance to keep', () => {
    expect(chips(served(), 'savings_balance')).toEqual([
      ['peak_spent', 'Peak month $480.00', 'amount'],
      ['peak_available', 'Peak balance $900.00', 'amount'],
    ])
  })

  it('offers nothing before the suggestions arrive, or with no months to read', () => {
    expect(chips(undefined, 'monthly_funding')).toEqual([])
    expect(chips(served({ months_counted: 0 }), 'monthly_funding')).toEqual([])
  })

  it('leaves out a figure the server had no answer for', () => {
    const quiet = served({
      average_spent: 0,
      peak_spent: null,
      peak_spent_month: null,
      peak_available: null,
      peak_available_month: null,
    })
    expect(chips(quiet, 'monthly_funding')).toEqual([])
  })

  it('says over how many months, and which month the peak was', () => {
    const [avg, peak] = suggestionChips(
      served({ months_counted: 3 }),
      'monthly_funding',
      money,
      month
    )
    expect(avg.title).toBe('Average spent per month over the last 3 months')
    expect(peak.title).toBe('Most spent in one month over the last 3 months (2026-03)')
    const [one] = suggestionChips(served({ months_counted: 1 }), 'monthly_funding', money, month)
    expect(one.title).toBe('Average spent per month over the last month')
  })

  it('writes the amount into the field as the input shows it', () => {
    const [avg] = suggestionChips(served({ average_spent: 212.5 }), 'monthly_funding', money, month)
    expect(chipInputValue(avg)).toBe('212.50')
  })
})
