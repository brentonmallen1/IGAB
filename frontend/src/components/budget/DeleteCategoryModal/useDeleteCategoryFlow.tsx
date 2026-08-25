import { useState } from 'react'
import { useAppStore } from '../../../stores/appStore'
import { useToastUndoChange } from '../../../utils/toastUndo'
import { DeleteCategoryModal } from './DeleteCategoryModal'
import type { DeleteTarget } from '../../../api/categories'

/**
 * The whole delete-a-category interaction, in one place.
 *
 * Three screens can start this (the inspector, the mobile action sheet, the
 * budget page's selection bar) and all three used to carry their own copy of
 * the confirmation — three copies of the same sentence, which is how they came
 * to say something that was no longer true. They now each ask for the flow and
 * render what it hands back.
 *
 *   const { requestDelete, modal } = useDeleteCategoryFlow(budgetId, onDone)
 *   …
 *   <button onClick={() => requestDelete({ kind: 'categories', ids, name })}>
 *   {modal}
 */
export function useDeleteCategoryFlow(budgetId: string, onDeleted?: () => void) {
  const month = useAppStore((s) => s.selectedMonth)
  const [target, setTarget] = useState<DeleteTarget | null>(null)
  const showUndo = useToastUndoChange(budgetId)

  const modal = target ? (
    <DeleteCategoryModal
      budgetId={budgetId}
      target={target}
      month={month}
      onClose={() => setTarget(null)}
      onDeleted={(changeId) => {
        showUndo(changeId, `${target.name} deleted`)
        onDeleted?.()
      }}
    />
  ) : null

  return { requestDelete: setTarget, modal }
}
