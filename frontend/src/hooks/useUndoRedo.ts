import { useCallback, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { apiClient } from '../api/client'
import { changesKeys, invalidateAfterUndo, useUndoChange, type Change } from '../api/changes'
import { useUpdateTransaction } from '../api/transactions'
import { useAppStore } from '../stores/appStore'
import { useHistoryStore } from '../stores/historyStore'
import { actionTypeLabel, entityTypeLabel } from '../pages/ActivityPage/changeLabels'

/**
 * Undo and redo, once, for every way of asking.
 *
 * ⌘Z lived inline in GlobalShortcuts; the header buttons would have been a
 * second copy of the same two-stack rule the day they were added, and the
 * palette a third. The rule: an inline register edit (client-side,
 * field-level) is undone first; with none pending, the newest server-recorded
 * change goes — a bulk assign, a cover, a delete — through the change log.
 * Undoing one row of a batch undoes the batch, which is what "undo Reset
 * Available" means.
 *
 * `busy` is a ref rather than state on purpose: it guards against a second
 * request while one is in flight without re-rendering every consumer.
 */
export function useUndoRedo() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const undoTxn = useUpdateTransaction(budgetId ?? '')
  const undoChange = useUndoChange(budgetId ?? '')
  const qc = useQueryClient()
  const inFlight = useRef(false)

  const undo = useCallback(async () => {
    const local = useHistoryStore.getState().undo()
    if (local) {
      undoTxn.mutate({ id: local.transactionId, [local.field]: local.before } as Parameters<
        typeof undoTxn.mutate
      >[0])
      return
    }
    if (!budgetId || inFlight.current) return
    inFlight.current = true
    try {
      const { data } = await apiClient.get<{ changes: Change[] }>(`/${budgetId}/changes`, {
        params: { limit: 20 },
      })
      const latest = data.changes.find((c) => !c.undone_at)
      if (!latest) {
        toast('Nothing to undo')
        return
      }
      // Every recorded change carries a batch id; only say "batch" when it
      // actually had siblings (a bulk assign, a cover, a multi-row delete).
      const siblings = latest.batch_id
        ? data.changes.filter((c) => c.batch_id === latest.batch_id).length
        : 1
      await undoChange.mutateAsync({ changeId: latest.id })
      invalidateAfterUndo(qc, budgetId)
      toast.success(
        `Undid: ${actionTypeLabel(latest.action).toLowerCase()} ${entityTypeLabel(latest.entity_type)}${siblings > 1 ? ` — and the other ${siblings - 1} in that batch` : ''}`
      )
    } catch {
      // useUndoChange already reports the failure
    } finally {
      inFlight.current = false
    }
  }, [budgetId, qc, undoChange, undoTxn])

  // Re-applies the most recently undone change; the server refuses once
  // anything newer has been recorded, so the toast explains the refusal.
  const redo = useCallback(async () => {
    if (!budgetId || inFlight.current) return
    inFlight.current = true
    try {
      await apiClient.post(`/${budgetId}/changes/redo`)
      qc.invalidateQueries({ queryKey: changesKeys.budget(budgetId) })
      invalidateAfterUndo(qc, budgetId)
      toast.success('Redone')
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: { message?: string } | string } } })
        ?.response?.data?.detail
      const message = typeof detail === 'string' ? detail : detail?.message
      toast(message ?? 'Nothing to redo')
    } finally {
      inFlight.current = false
    }
  }, [budgetId, qc])

  return { undo, redo, enabled: !!budgetId }
}
