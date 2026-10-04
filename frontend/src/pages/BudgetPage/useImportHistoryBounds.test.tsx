/**
 * The budget page's month bounds for an imported budget: read-only months
 * from YNAB's kept figures up to the anchor, and none of them leaking to the
 * other pages that share the selected month.
 */
import { renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { useAppStore } from '../../stores/appStore'
import type { BudgetMonth } from '../../types'
import { useImportHistoryBounds } from './useImportHistoryBounds'

const served = (over: Partial<BudgetMonth>): BudgetMonth =>
  ({
    anchor_month: '2026-08-01',
    history_starts: '2026-06-01',
    read_only: false,
    ...over,
  }) as BudgetMonth

afterEach(() => {
  const s = useAppStore.getState()
  s.setBudgetAnchorMonth(null)
  s.setBudgetHistoryStarts(null)
})

describe('the budget page’s month bounds', () => {
  it('shows a read-only month the kept figures reach', () => {
    const { result } = renderHook(() =>
      useImportHistoryBounds(served({ read_only: true }), '2026-07-01')
    )
    expect(result.current.showHistory).toBe(true)
  })

  it('shows the live budget from the import month on', () => {
    const { result } = renderHook(() => useImportHistoryBounds(served({}), '2026-08-01'))
    expect(result.current.showHistory).toBe(false)
  })

  it('shows no history where the import kept none', () => {
    const { result } = renderHook(() =>
      useImportHistoryBounds(served({ read_only: true, history_starts: null }), '2026-07-01')
    )
    expect(result.current.showHistory).toBe(false)
  })

  it('snaps back to the import month when the page is left on a read-only month', () => {
    useAppStore.getState().setSelectedMonth('2026-07-01')
    const { unmount } = renderHook(() =>
      useImportHistoryBounds(served({ read_only: true }), '2026-07-01')
    )
    expect(useAppStore.getState().selectedMonth).toBe('2026-07-01')
    unmount()
    expect(useAppStore.getState().selectedMonth).toBe('2026-08-01')
  })

  it('leaves a later month alone on the way out', () => {
    useAppStore.getState().setSelectedMonth('2026-09-01')
    const { unmount } = renderHook(() => useImportHistoryBounds(served({}), '2026-09-01'))
    unmount()
    expect(useAppStore.getState().selectedMonth).toBe('2026-09-01')
  })
})
