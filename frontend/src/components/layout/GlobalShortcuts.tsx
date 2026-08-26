import { useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useAppStore } from '../../stores/appStore'
import { useShortcut } from '../../hooks/useShortcut'
import { SHORTCUTS } from '../../keyboard/shortcuts'
import { ShortcutHelp } from '../common/ShortcutHelp/ShortcutHelp'
import { addMonths, currentMonthStart } from '../../utils/dates'
import toast from 'react-hot-toast'
import { apiClient } from '../../api/client'
import { useQueryClient } from '@tanstack/react-query'
import { changesKeys, invalidateAfterUndo, useUndoChange, type Change } from '../../api/changes'
import { useUpdateTransaction } from '../../api/transactions'
import { useHistoryStore } from '../../stores/historyStore'
import { actionTypeLabel, entityTypeLabel } from '../../pages/ActivityPage/changeLabels'

/** App-wide shortcut registrations + the '?' help overlay. */
export function GlobalShortcuts() {
  const selectedMonth = useAppStore((s) => s.selectedMonth)
  const setSelectedMonth = useAppStore((s) => s.setSelectedMonth)
  const togglePrivacyMode = useAppStore((s) => s.togglePrivacyMode)
  const [helpOpen, setHelpOpen] = useState(false)
  // Month nav only exists on the budget page; firing these elsewhere would
  // change the month invisibly.
  const onBudgetPage = useLocation().pathname === '/budget'

  useShortcut(SHORTCUTS.help.combo, () => setHelpOpen((o) => !o))
  useShortcut('escape', () => setHelpOpen(false), { enabled: helpOpen, allowInInputs: true })
  useShortcut(SHORTCUTS.monthPrev.combo, () => setSelectedMonth(addMonths(selectedMonth, -1)), {
    enabled: onBudgetPage,
  })
  useShortcut(SHORTCUTS.monthNext.combo, () => setSelectedMonth(addMonths(selectedMonth, 1)), {
    enabled: onBudgetPage,
  })
  useShortcut(SHORTCUTS.monthToday.combo, () => setSelectedMonth(currentMonthStart()), {
    enabled: onBudgetPage,
  })
  useShortcut(SHORTCUTS.privacy.combo, togglePrivacyMode)

  // ⌘Z. Two undo stacks converge here so the key means one thing everywhere:
  // an inline register edit (client-side, field-level) is undone first; with
  // none pending, the newest server-recorded change is undone — a bulk
  // assign, a cover, a delete — via the change log. Undoing one row of a
  // batch undoes the batch, which is what "undo Reset Available" means.
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const undoTxn = useUpdateTransaction(budgetId ?? '')
  const undoChange = useUndoChange(budgetId ?? '')
  const qc = useQueryClient()
  const undoInFlight = useRef(false)
  useShortcut(SHORTCUTS.undo.combo, async () => {
    const local = useHistoryStore.getState().undo()
    if (local) {
      undoTxn.mutate({ id: local.transactionId, [local.field]: local.before } as Parameters<typeof undoTxn.mutate>[0])
      return
    }
    if (!budgetId || undoInFlight.current) return
    undoInFlight.current = true
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
      undoInFlight.current = false
    }
  })

  // ⌘⇧Z re-applies the most recently undone change; the server refuses once
  // anything newer has been recorded, so the toast explains the refusal.
  useShortcut(SHORTCUTS.redo.combo, async () => {
    if (!budgetId || undoInFlight.current) return
    undoInFlight.current = true
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
      undoInFlight.current = false
    }
  })

  if (!helpOpen) return null
  return <ShortcutHelp onClose={() => setHelpOpen(false)} />
}
