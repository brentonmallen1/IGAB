/**
 * Toast with an inline Undo button for destructive actions.
 *
 * Usage:
 *   const showUndo = useToastUndo(budgetId, accountId)
 *   showUndo(batchId, 'Transaction deleted')
 *
 *   const showUndo = useToastUndoChange(budgetId)
 *   showUndo(changeId, 'Groceries deleted')
 *
 * Clicking Undo calls the undo endpoint and invalidates the standard caches.
 *
 * Two entry points because compound operations are recorded two ways. Most
 * write a change row per affected entity sharing a batch_id. A category
 * delete writes exactly one row carrying its own bookkeeping — a batch of one
 * row per transaction would be thousands of rows and thousands of undo buttons
 * — so it is addressed by change id. The endpoints converge: undoing a change
 * that belongs to a batch undoes the batch.
 */
import { useCallback } from 'react'
import toast from 'react-hot-toast'
import { useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import { invalidateAfterUndo, changesKeys } from '../api/changes'

/** Undo one change row by id (`/changes/{id}/undo`). */
export function useToastUndoChange(budgetId: string, accountId?: string | null) {
  return useUndoToast(budgetId, accountId, (id) => `/${budgetId}/changes/${id}/undo`)
}

/** Undo a whole batch by batch id (`/changes/batch/{id}/undo`). */
export function useToastUndo(budgetId: string, accountId?: string | null) {
  return useUndoToast(budgetId, accountId, (id) => `/${budgetId}/changes/batch/${id}/undo`)
}

function useUndoToast(
  budgetId: string,
  accountId: string | null | undefined,
  path: (id: string) => string
) {
  const qc = useQueryClient()

  return useCallback(
    (batchId: string | null | undefined, message: string) => {
      if (!batchId) {
        // No undo available (e.g. nothing actually changed)
        toast.success(message)
        return
      }

      toast.success(
        (t) => (
          <span className="toast-undo-content">
            {message}
            <button
              type="button"
              className="toast-undo-button"
              onClick={async () => {
                toast.dismiss(t.id)
                try {
                  await apiClient.post(path(batchId))
                  qc.invalidateQueries({ queryKey: changesKeys.budget(budgetId) })
                  invalidateAfterUndo(qc, budgetId, accountId)
                  toast.success('Undone')
                } catch (err) {
                  // Extract error message from API response if available
                  let msg = 'Could not undo'
                  if (err && typeof err === 'object' && 'response' in err) {
                    const resp = (err as { response?: { data?: { detail?: { message?: string } | string } } }).response
                    const detail = resp?.data?.detail
                    if (typeof detail === 'string') msg = detail
                    else if (detail?.message) msg = detail.message
                  }
                  toast.error(msg)
                }
              }}
            >
              Undo
            </button>
          </span>
        ),
        { duration: 5000 }
      )
    },
    [budgetId, accountId, qc, path]
  )
}
