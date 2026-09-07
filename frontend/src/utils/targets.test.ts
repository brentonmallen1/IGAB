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
import { targetMeasuresBalance, targetProgress } from './targets'
import type { CategoryTarget } from '../types'

function target(overrides: Partial<CategoryTarget> = {}): CategoryTarget {
  return {
    category_id: 'c1',
    target_type: 'monthly_funding',
    target_amount: 100,
    target_date: null,
    check_after_day: null,
    weekday: null,
    ...overrides,
  } as unknown as CategoryTarget
}

describe('which number fills the bar', () => {
  it('a funding target fills by assigned', () => {
    expect(targetProgress(target(), 50, 0)).toBe(0.5)
  })

  it('a weekly target fills by assigned too', () => {
    expect(targetProgress(target({ target_type: 'weekly_funding', weekday: 4 }), 25, 0)).toBe(0.25)
  })

  it('a savings-balance target fills by available', () => {
    const t = target({ target_type: 'savings_balance', target_amount: 1000 })
    expect(targetProgress(t, 0, 250)).toBe(0.25)
  })

  it('a dated savings-balance target still fills by available — goal progress, not pace', () => {
    const t = target({
      target_type: 'savings_balance',
      target_amount: 600,
      target_date: '2026-12-01',
    })
    expect(targetProgress(t, 0, 300)).toBe(0.5)
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

describe('targetMeasuresBalance is wording only', () => {
  it('is true for an undated savings balance and nothing else', () => {
    expect(targetMeasuresBalance(target({ target_type: 'savings_balance' }))).toBe(true)
    expect(
      targetMeasuresBalance(target({ target_type: 'savings_balance', target_date: '2026-12-01' }))
    ).toBe(false)
    expect(targetMeasuresBalance(target())).toBe(false)
    expect(targetMeasuresBalance(target({ target_type: 'weekly_funding' }))).toBe(false)
  })
})

describe('the server owns the verdict', () => {
  it('exports no status or shortfall function', async () => {
    // The list is exact on purpose: a second opinion about whether a target is
    // met is exactly what this module must never grow. MAX_FUNDING_DAY is a
    // shared BOUND, not a verdict — the same number the server validates
    // against, so the form refuses what the API would refuse.
    const mod = await import('./targets')
    expect(Object.keys(mod).sort()).toEqual([
      'MAX_FUNDING_DAY',
      'targetMeasuresBalance',
      'targetProgress',
    ])
  })
})
