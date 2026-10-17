import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import type { BudgetMonth, CategoryHistory, AutoAssignAction } from '../types'
import { ROOT } from './queryKeys'
import { invalidateAfterMoneyMove } from './invalidateAfterMoneyMove'
import { withAssignments } from '../utils/categoryBalances'

/**
 * Assigned and spent over the months before `month`, per category — the
 * figures on the inspector's history buttons.
 *
 * The month is sent and is part of the key. It was neither: the server fell
 * back to today, so on any other month the buttons showed this month's
 * history while the press — which does send the month — applied that month's,
 * and the figure on the button was not the figure it set.
 */
export function useCategoryHistoryBatch(
  budgetId: string | null,
  categoryIds: string[],
  month: string
) {
  return useQuery({
    queryKey: [ROOT.categoryHistoryBatch, budgetId, month, categoryIds],
    queryFn: async () => {
      const { data } = await apiClient.post<CategoryHistory[]>(
        `/${budgetId}/categories/history/batch`,
        { category_ids: categoryIds },
        { params: { month } }
      )
      return data
    },
    enabled: !!budgetId && categoryIds.length > 0,
    staleTime: 60_000,
  })
}

export interface AutoAssignVariables {
  categoryIds: string[]
  action: AutoAssignAction
  /** What each envelope will hold (`autoAssignAmounts`), drawn at once while
   *  the server writes it. Null when the figures are not known yet — then
   *  the grid waits for the server instead of guessing. */
  amounts: Map<string, number> | null
}

export function useAutoAssign(budgetId: string, month: string) {
  const qc = useQueryClient()
  const key = [ROOT.budgetMonth, budgetId, month]
  return useMutation({
    mutationFn: ({ categoryIds, action }: AutoAssignVariables) =>
      apiClient
        .post(`/${budgetId}/categories/auto-assign`, { category_ids: categoryIds, action, month })
        .then((r) => r.data),
    // Optimistic, as a typed cell is: the envelopes show their new figures
    // at once, and the refetch below replaces them with the server's.
    onMutate: async ({ amounts }) => {
      await qc.cancelQueries({ queryKey: key })
      const previous = qc.getQueryData<BudgetMonth>(key)
      if (previous && amounts) {
        qc.setQueryData<BudgetMonth>(key, withAssignments(previous, month, amounts))
      }
      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) qc.setQueryData(key, context.previous)
    },
    onSettled: () => invalidateAfterMoneyMove(qc, budgetId),
  })
}
