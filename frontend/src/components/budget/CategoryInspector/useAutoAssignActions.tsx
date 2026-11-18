import { useState } from 'react'
import { useCategories } from '../../../api/categories'
import { useAutoAssign } from '../../../api/categoryHistory'
import { useAppStore } from '../../../stores/appStore'
import type { AutoAssignAction, CategoryBalance, CategoryHistory } from '../../../types'
import { coverRows, initialCoverIds, shouldAskTargetCover } from '../../../utils/targetCover'
import { autoAssignAmounts, autoAssignRows } from './autoAssignActions'
import { TargetCoverDialog } from './TargetCoverDialog'

/**
 * The inspector's Auto-Assign buttons, wired: the rows, what a press sends,
 * and — with several envelopes selected and some of them overspent — the
 * Target / Cover + target question in between. The single category's
 * section and the month summary both press through this, so the question is
 * asked the same way from either.
 *
 * `targetCoverMode` (device-local) decides the question: `ask` opens the
 * dialog, `target` sends no `cover_ids`, `cover` sends every offered one.
 */
export function useAutoAssignActions(
  budgetId: string,
  month: string,
  categoryIds: string[],
  histories: readonly CategoryHistory[] | undefined,
  balances: readonly CategoryBalance[] | undefined
) {
  const autoAssign = useAutoAssign(budgetId, month)
  const mode = useAppStore((s) => s.targetCoverMode)
  const { data: categories } = useCategories(budgetId)
  const [asking, setAsking] = useState(false)

  const nameOf = (id: string) => categories?.find((c) => c.id === id)?.name ?? 'Category'
  // One category gets its own Cover + target row; the question is for several.
  const offered = categoryIds.length > 1 ? coverRows(categoryIds, balances ?? [], nameOf) : []
  const initialCover = initialCoverIds(
    mode,
    offered.map((r) => r.categoryId)
  )
  const defaultCover = new Set(initialCover)
  const rows = autoAssignRows(categoryIds, histories, balances, defaultCover)

  const send = (action: AutoAssignAction, coverIds: ReadonlySet<string>) => ({
    categoryIds,
    action,
    coverIds: action === 'target_amount' ? [...coverIds] : [],
    amounts: autoAssignAmounts(action, categoryIds, histories, balances, coverIds),
  })

  /** A row's press. A row that names its own `coverIds` (the single
   *  category's Cover + target) sends them; Target Amount over several asks
   *  first under `ask`, or sends the setting's default. */
  function press({ action, coverIds }: { action: AutoAssignAction; coverIds?: string[] }) {
    if (coverIds) {
      autoAssign.mutate(send(action, new Set(coverIds)))
      return
    }
    if (action === 'target_amount' && shouldAskTargetCover(mode, offered.length)) {
      setAsking(true)
      return
    }
    autoAssign.mutate(send(action, defaultCover))
  }

  const targeted = autoAssignAmounts('target_amount', categoryIds, histories, balances)?.size ?? 0
  const dialog = asking ? (
    <TargetCoverDialog
      rows={offered}
      othersCount={targeted - offered.length}
      initialCoverIds={initialCover}
      onConfirm={(coverIds) => autoAssign.mutateAsync(send('target_amount', new Set(coverIds)))}
      onClose={() => setAsking(false)}
    />
  ) : null

  return { rows, press, isPending: autoAssign.isPending, dialog }
}
