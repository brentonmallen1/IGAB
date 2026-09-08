/**
 * Success toasts that can take themselves back.
 *
 *   const notify = useUndoToast(accountId)
 *   notify('Transaction deleted', { batch: result.batch_id })   // precise
 *   notify('Groceries deleted', { change: result.change_id })  // precise
 *   notify('Assigned $40 to Groceries', 'latest')              // newest change
 *   notify('Saved')                                            // no undo
 *
 * One implementation of the Undo button, wired to the one undo
 * (`performUndo` in api/changes). It used to have two: this file posted the
 * batch endpoint and parsed the 409 itself while useUndoRedo did the same for
 * ⌘Z, and the two composed different sentences for the same outcome.
 *
 * Why `latest` is safe enough to offer: the toast remembers the change-log
 * head it saw when it was shown and asks again before undoing. If anything
 * has landed since — an inline edit, a sync — it declines and points at the
 * Activity page rather than undoing the wrong thing. And every undoable toast
 * shares one id, so a newer one replaces the older: an Undo button never
 * outlives the action it names.
 */
import { useCallback } from 'react'
import toast from 'react-hot-toast'
import { useQueryClient } from '@tanstack/react-query'
import { useAppStore } from '../stores/appStore'
import { conflictMessage, fetchChangeHead, performUndo, type UndoTarget } from '../api/changes'
import { undoneMessage } from './undoneMessage'

/** One id for every undoable toast: the newest replaces the rest. */
export const UNDOABLE_TOAST_ID = 'undoable'
export const UNDOABLE_TOAST_MS = 5000

export const HEAD_MOVED_MESSAGE = 'Something changed since — undo it from the Activity page'

export type NotifyUndoable = (message: string, target?: UndoTarget | null) => void

export function useUndoToast(accountId?: string | null): NotifyUndoable {
  const qc = useQueryClient()
  const budgetId = useAppStore((s) => s.currentBudgetId)

  return useCallback(
    (message, target) => {
      if (!target || !budgetId) {
        toast.success(message)
        return
      }

      // Captured now, checked at click time. Rejected promise → head unknown
      // → the button still declines, never guesses.
      const headSeen = target === 'latest' ? fetchChangeHead(budgetId).catch(() => -1) : null

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
                  if (headSeen) {
                    const [seen, now] = await Promise.all([headSeen, fetchChangeHead(budgetId)])
                    if (seen < 0 || now !== seen) {
                      toast(HEAD_MOVED_MESSAGE)
                      return
                    }
                  }
                  const data = await performUndo(qc, budgetId, target, accountId)
                  toast.success(undoneMessage(data))
                } catch (err) {
                  toast.error(conflictMessage(err) ?? 'Could not undo')
                }
              }}
            >
              Undo
            </button>
          </span>
        ),
        { id: UNDOABLE_TOAST_ID, duration: UNDOABLE_TOAST_MS }
      )
    },
    [budgetId, accountId, qc]
  )
}
