import { describe, expect, it } from 'vitest'
import { buildTargetPayload, TARGET_TYPES } from './targetForm'

const base = {
  targetType: 'monthly_funding',
  amount: '100',
  targetDate: '',
  weekday: '',
  checkAfterDay: '',
}

describe('buildTargetPayload', () => {
  it('offers exactly three shapes', () => {
    expect(TARGET_TYPES.map((t) => t.value)).toEqual([
      'monthly_funding',
      'weekly_funding',
      'savings_balance',
    ])
  })

  it('refuses an unreadable or zero amount rather than writing $0', () => {
    expect(buildTargetPayload({ ...base, amount: 'abc' })).toEqual({
      ok: false,
      error: 'Enter an amount.',
    })
    expect(buildTargetPayload({ ...base, amount: '0' }).ok).toBe(false)
  })

  it('a weekly target requires its weekday', () => {
    expect(buildTargetPayload({ ...base, targetType: 'weekly_funding' }).ok).toBe(false)
    const r = buildTargetPayload({ ...base, targetType: 'weekly_funding', weekday: '4' })
    expect(r.ok && r.payload.weekday).toBe(4)
  })

  it('drops a stale date for anything but a savings balance', () => {
    const r = buildTargetPayload({ ...base, targetDate: '2026-12-01' })
    expect(r.ok && r.payload.target_date).toBeNull()
    const s = buildTargetPayload({
      ...base,
      targetType: 'savings_balance',
      targetDate: '2026-12-01',
    })
    expect(s.ok && s.payload.target_date).toBe('2026-12-01')
  })

  it('drops a weekday for anything but weekly', () => {
    const r = buildTargetPayload({ ...base, weekday: '2' })
    expect(r.ok && r.payload.weekday).toBeNull()
  })

  it('bounds the check-after day to 1..28 and sends null for blank', () => {
    expect(buildTargetPayload({ ...base, checkAfterDay: '29' }).ok).toBe(false)
    const r = buildTargetPayload({ ...base, checkAfterDay: '15' })
    expect(r.ok && r.payload.check_after_day).toBe(15)
    const blank = buildTargetPayload(base)
    expect(blank.ok && blank.payload.check_after_day).toBeNull()
  })
})
