import { useCallback, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { apiClient } from '../api/client'
import { changesKeys, invalidateAfterUndo, type UndoLatestResponse } from '../api/changes'
import { useAppStore } from '../stores/appStore'
import { actionTypeLabel, entityTypeLabel } from '../pages/ActivityPage/changeLabels'

/**
 * Undo and redo, once, for every way of asking — ⌘Z, the header buttons, the
 * Activity page's redo affordance.
 *
 * One stack, and it lives on the server. There used to be two: a client-side
 * shadow stack of inline register edits that ⌘Z preferred unconditionally,
 * was never cleared, and never learned about anything else the user did — so
 * after an inline memo edit, ⌘Z on a deleted transaction popped the stale
 * memo instead of the delete, and the compensating PATCH then recorded a NEW
 * change row that the next ⌘Z undid, re-applying the first edit. Every
 * inline edit already records a server `update` row; the shadow stack was a
 * second representation of the same action, and deleting it is the fix.
 *
 * Selection is the server's too (`POST /changes/undo`): newest live MANUAL
 * change, whole batch if it has one. Background writers — SimpleFIN sync,
 * the AI worker, the scheduler — are skipped by source, so a sync landing
 * between the user's action and their ⌘Z is never what gets undone. The
 * Activity page can still undo anything by id.
 *
 * `inFlight` is a ref rather than state on purpose: it guards against a
 * second request while one is in flight without re-rendering every consumer.
 */
export function useUndoRedo() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const qc = useQueryClient()
  const inFlight = useRef(false)

  const undo = useCallback(async () => {
    if (!budgetId || inFlight.current) return
    inFlight.current = true
    try {
      const { data } = await apiClient.post<UndoLatestResponse>(`/${budgetId}/changes/undo`)
      qc.invalidateQueries({ queryKey: changesKeys.budget(budgetId) })
      invalidateAfterUndo(qc, budgetId)
      const others = data.undone_change_ids.length - 1
      toast.success(
        `Undid: ${actionTypeLabel(data.action).toLowerCase()} ${entityTypeLabel(data.entity_type, data.action)}${others > 0 ? ` — and the other ${others} in that batch` : ''}`
      )
    } catch (err: unknown) {
      toast(conflictMessage(err) ?? 'Nothing to undo')
    } finally {
      inFlight.current = false
    }
  }, [budgetId, qc])

  // Re-applies the most recently undone change; the server refuses once
  // anything newer is live, so the toast explains the refusal.
  const redo = useCallback(async () => {
    if (!budgetId || inFlight.current) return
    inFlight.current = true
    try {
      await apiClient.post(`/${budgetId}/changes/redo`)
      qc.invalidateQueries({ queryKey: changesKeys.budget(budgetId) })
      invalidateAfterUndo(qc, budgetId)
      toast.success('Redone')
    } catch (err: unknown) {
      toast(conflictMessage(err) ?? 'Nothing to redo')
    } finally {
      inFlight.current = false
    }
  }, [budgetId, qc])

  return { undo, redo, enabled: !!budgetId }
}

/** The message inside a 409's structured detail, if the error carries one. */
function conflictMessage(err: unknown): string | undefined {
  const detail = (err as { response?: { data?: { detail?: { message?: string } | string } } })
    ?.response?.data?.detail
  return typeof detail === 'string' ? detail : detail?.message
}
