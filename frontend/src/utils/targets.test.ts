/**
 * What is left in utils/targets is bar geometry.
 *
 * Note what is no longer tested here: whether a target is funded, and how much
 * it still needs. Those had two implementations in this file and a third in
 * CategoryRow, and all three disagreed — the monthly-pace division was applied
 * to the wrong target type, the month clamp differed, and the pill and the
 * "Save $X more" beside it were computed from different rules. They now arrive
 * on the row as `target_status` and `needed_this_month`, from the same service
 * Fill Underfunded asks. The last describe block exists to keep it that way.
 */
import { describe, expect, it } from 'vitest'
import { monthsUntil, targetMeasuresBalance, targetProgress } from './targets'
import type { CategoryTarget } from '../types'

function target(overrides: Partial<CategoryTarget> = {}): CategoryTarget {
  return {
    category_id: 'c1',
    target_type: 'monthly_funding',
    target_amount: 100,
    target_date: null,
    ...overrides,
  } as unknown as CategoryTarget
}

describe('which number fills the bar', () => {
  it('a funding target fills by assigned', () => {
    expect(targetProgress(target(), 50, 0)).toBe(0.5)
  })

  it('a savings-balance target fills by available', () => {
    const t = target({ target_type: 'savings_balance', target_amount: 1000 })
    expect(targetProgress(t, 0, 250)).toBe(0.25)
  })

  it('a dated needed-for-spending target fills by available', () => {
    const t = target({
      target_type: 'needed_for_spending',
      target_amount: 600,
      target_date: '2026-12-01',
    })
    expect(targetProgress(t, 0, 300)).toBe(0.5)
  })

  it('an undated needed-for-spending target fills by assigned', () => {
    const t = target({ target_type: 'needed_for_spending', target_amount: 600, target_date: null })
    expect(targetProgress(t, 300, 0)).toBe(0.5)
  })

  it('clamps to 0..1 rather than overflowing the track', () => {
    expect(targetProgress(target(), 250, 0)).toBe(1)
    expect(targetProgress(target(), -50, 0)).toBe(0)
  })

  it('has no answer for a zero or negative target', () => {
    expect(targetProgress(target({ target_amount: 0 }), 10, 10)).toBeNull()
    expect(targetProgress(target({ target_amount: -5 }), 10, 10)).toBeNull()
  })
})

describe('targetMeasuresBalance', () => {
  it('is true for the two balance-shaped targets', () => {
    expect(targetMeasuresBalance(target({ target_type: 'savings_balance' }))).toBe(true)
    expect(
      targetMeasuresBalance(
        target({ target_type: 'needed_for_spending', target_date: '2026-12-01' })
      )
    ).toBe(true)
  })

  it('is false for funding duties', () => {
    expect(targetMeasuresBalance(target({ target_type: 'monthly_funding' }))).toBe(false)
    expect(targetMeasuresBalance(target({ target_type: 'weekly_funding' }))).toBe(false)
    expect(
      targetMeasuresBalance(target({ target_type: 'needed_for_spending', target_date: null }))
    ).toBe(false)
  })
})

describe('monthsUntil', () => {
  const now = new Date('2026-08-15T12:00:00')

  it('counts whole months', () => {
    expect(monthsUntil('2026-11-01', now)).toBe(3)
  })

  it('ignores the day, like the backend does', () => {
    expect(monthsUntil('2026-09-28', now)).toBe(1)
  })

  it('floors at one for this month', () => {
    expect(monthsUntil('2026-08-01', now)).toBe(1)
  })

  it('floors at one for a date already past', () => {
    expect(monthsUntil('2025-01-01', now)).toBe(1)
  })

  it('crosses a year', () => {
    expect(monthsUntil('2027-02-01', now)).toBe(6)
  })
})

describe('the server owns the verdict', () => {
  // The guard rail. If someone reintroduces a funded/needed rule here, these
  // fail — the module must not grow a way to answer those questions.
  it('exports no status rule', async () => {
    const mod = await import('./targets')
    expect(Object.keys(mod).sort()).toEqual([
      'monthsUntil',
      'targetMeasuresBalance',
      'targetProgress',
    ])
  })
})
