import { useCallback } from 'react'
import { useRecordCardDue } from '../api/cardDueDismissals'
import { useAppStore } from '../stores/appStore'
import { useUndoToast } from '../utils/toastUndo'
import { useFormatters } from './useFormatters'

/**
 * "Mark paid" on a card's bill, for every surface that offers it — the
 * app-wide banner and the credit-cards strip. One wiring, so the two cannot
 * store the key differently or say different things about it.
 *
 * Stores a `paid` key (`api/cardDueDismissals.ts`), which the reminder rule
 * reads as that bill paid (`utils/paymentDue.ts`); the toast's Undo takes it
 * back through the change log, as ⌘Z does.
 */
export function useMarkBillPaid() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const record = useRecordCardDue(budgetId)
  const notify = useUndoToast()
  const { formatDayMonth } = useFormatters()

  const mark = useCallback(
    (accountId: string, name: string, dueDate: string) =>
      record.mutate(
        { accountId, dueDate, state: 'paid' },
        {
          onSuccess: () =>
            notify(`${name}'s bill due ${formatDayMonth(dueDate)} marked paid`, 'latest'),
        }
      ),
    [record, notify, formatDayMonth]
  )
  return { mark, isPending: record.isPending }
}
