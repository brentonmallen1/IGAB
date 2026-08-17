/**
 * Toast with an inline Undo button for destructive actions.
 *
 * Usage:
 *   const showUndo = useToastUndo(budgetId, accountId)
 *   showUndo(batchId, 'Transaction deleted')
 *
 * Clicking Undo calls the undo endpoint and invalidates the standard caches.
 */
import { useCallback } from 'react'
import toast from 'react-hot-toast'
import { useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import { invalidateAfterUndo, changesKeys } from '../api/changes'

export function useToastUndo(budgetId: string, accountId?: string | null) {
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
                  await apiClient.post(`/${budgetId}/changes/batch/${batchId}/undo`)
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
    [budgetId, accountId, qc]
  )
}
