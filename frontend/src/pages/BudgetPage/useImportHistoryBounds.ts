import { useEffect, useRef } from 'react'
import { monthFloor, useAppStore } from '../../stores/appStore'
import type { BudgetMonth } from '../../types'

/**
 * The budget page's side of an imported budget's month bounds, from the
 * served month: the anchor and the start of YNAB's kept figures go into the
 * store (whose `setSelectedMonth` clamps every navigation surface against
 * them), a month below the floor clamps forward, and leaving the page on a
 * read-only month snaps back to the import month.
 *
 * That last one exists because the selected month is shared: Reports'
 * overview and the integrity panel read it too, and none of them can show a
 * month before the import honestly. Read-only months are this page's.
 *
 * Returns whether to show the month as YNAB's read-only figures — a served
 * answer (`read_only`) where the kept figures reach it, never a month
 * comparison of the client's own.
 */
export function useImportHistoryBounds(budgetMonth: BudgetMonth | undefined, month: string) {
  const setSelectedMonth = useAppStore((s) => s.setSelectedMonth)
  const setBudgetAnchorMonth = useAppStore((s) => s.setBudgetAnchorMonth)
  const setBudgetHistoryStarts = useAppStore((s) => s.setBudgetHistoryStarts)
  const anchorMonth = budgetMonth?.anchor_month ?? null
  // Null on an import that kept no figures: the page stops at the anchor.
  const historyStarts = budgetMonth?.history_starts ?? null

  useEffect(() => {
    setBudgetAnchorMonth(anchorMonth)
    return () => setBudgetAnchorMonth(null)
  }, [anchorMonth, setBudgetAnchorMonth])
  useEffect(() => {
    setBudgetHistoryStarts(historyStarts)
    return () => setBudgetHistoryStarts(null)
  }, [historyStarts, setBudgetHistoryStarts])
  useEffect(() => {
    // A persisted month from before the floor (or another budget) clamps
    // forward the moment the floor is known — the store's own rule.
    const floor = monthFloor({ budgetAnchorMonth: anchorMonth, budgetHistoryStarts: historyStarts })
    if (floor && month < floor) setSelectedMonth(floor)
  }, [anchorMonth, historyStarts, month, setSelectedMonth])

  const anchorRef = useRef(anchorMonth)
  useEffect(() => {
    anchorRef.current = anchorMonth
  }, [anchorMonth])
  useEffect(
    () => () => {
      const anchor = anchorRef.current
      const { selectedMonth, setSelectedMonth: set } = useAppStore.getState()
      if (anchor && selectedMonth < anchor) set(anchor)
    },
    []
  )

  const showHistory =
    !!budgetMonth?.read_only && !!anchorMonth && !!historyStarts && month >= historyStarts
  return { anchorMonth, showHistory }
}
