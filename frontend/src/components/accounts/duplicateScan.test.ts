import { describe, expect, it } from 'vitest'
import {
  keepAllSeparateQuestion,
  DEFAULT_DUPLICATE_SCAN_SCOPE,
  LOOKBACK_CHOICES,
  normalizeScanScope,
  scanSince,
  scopePhrase,
} from './duplicateScan'

describe('the duplicate scan scope', () => {
  it('starts narrow: recent rows, nothing reconciled', () => {
    // The scan used to compare the whole account with itself, and every pair
    // it queued held the reconciliation back.
    expect(DEFAULT_DUPLICATE_SCAN_SCOPE).toEqual({ lookbackDays: 90, includeReconciled: false })
    expect(LOOKBACK_CHOICES.map((c) => c.days)).toEqual([30, 90, 365, null])
  })

  it('counts back in local calendar days', () => {
    expect(scanSince(30, '2026-11-24')).toBe('2026-10-25')
    expect(scanSince(90, '2026-03-01')).toBe('2025-12-01')
    expect(scanSince(365, '2026-11-24')).toBe('2025-11-24')
  })

  it('sends no date for all time', () => {
    expect(scanSince(null, '2026-11-24')).toBeUndefined()
  })

  it('keeps a remembered choice, all time included', () => {
    expect(normalizeScanScope({ lookbackDays: null, includeReconciled: true })).toEqual({
      lookbackDays: null,
      includeReconciled: true,
    })
    expect(normalizeScanScope({ lookbackDays: 30, includeReconciled: false })).toEqual({
      lookbackDays: 30,
      includeReconciled: false,
    })
  })

  it('reads anything it does not offer as the default, never as unbounded', () => {
    expect(normalizeScanScope(undefined)).toEqual(DEFAULT_DUPLICATE_SCAN_SCOPE)
    expect(normalizeScanScope({ lookbackDays: 7 })).toEqual(DEFAULT_DUPLICATE_SCAN_SCOPE)
    expect(normalizeScanScope({ lookbackDays: undefined, includeReconciled: 'yes' })).toEqual(
      DEFAULT_DUPLICATE_SCAN_SCOPE
    )
  })

  it('asks before keeping several pairs separate at once, and not for one', () => {
    expect(keepAllSeparateQuestion(0)).toBeNull()
    expect(keepAllSeparateQuestion(1)).toBeNull()
    expect(keepAllSeparateQuestion(7)).toMatchObject({
      title: 'Keep all 7 pairs separate?',
      confirmLabel: 'Keep 7 separate',
    })
    expect(keepAllSeparateQuestion(7)?.message).toMatch(/won’t be suggested as duplicates again/)
  })

  it('says where it looked, so nothing found is not read as nothing anywhere', () => {
    expect(scopePhrase({ lookbackDays: 90, includeReconciled: false })).toBe(
      'in the last 90 days, reconciled ones aside'
    )
    expect(scopePhrase({ lookbackDays: 365, includeReconciled: true })).toBe('in the last year')
    expect(scopePhrase({ lookbackDays: null, includeReconciled: true })).toBe('in this account')
  })
})
