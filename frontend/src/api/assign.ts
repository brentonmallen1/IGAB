import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import type { AssignStrategy } from '../types'
import { ROOT } from './queryKeys'
import { invalidateAfterMoneyMove } from './invalidateAfterMoneyMove'

export interface AssignStrategyTotal {
  strategy: AssignStrategy
  total_amount: number
  total_needed: number | null
  to_assign: number
  to_return: number
  affected_count: number
}

export interface AssignStrategyTotalsResponse {
  month: string
  tba: number
  /** The whole red — what the Cover Overspending row shows, matching the
   *  hero chip and the dialog it opens. */
  total_overspent: number
  /** How much of that rode onto a card. The same pair `BudgetMonth` carries,
   *  so both surfaces read one `overspending()` (budgetTotals). */
  total_overspent_credit: number
  strategies: AssignStrategyTotal[]
}

export interface AssignPreviewItem {
  category_id: string
  category_name: string
  current_assigned: number
  delta: number
  new_assigned: number
  /** Target Amount only: what this row reads under Target and under Cover +
   *  target, on a row offered that choice (both null otherwise).
   *  `new_assigned` is the one the request's `cover_ids` picked. Home:
   *  `AssignPreviewItem` (backend assign_service.py). */
  target_assigned: number | null
  cover_target_assigned: number | null
}

export interface AssignPreviewResponse {
  strategy: AssignStrategy
  items: AssignPreviewItem[]
  total_needed: number | null
  to_assign: number
  to_return: number
  tba_before: number
  tba_after: number
  /** Envelopes this strategy would leave newly in the red, and by how much.
   *  Home: `AssignPreview.newly_overspent_*` (backend assign_service.py) —
   *  the client cannot derive it, since the preview carries assigned figures
   *  and this is about available. */
  newly_overspent_count: number
  newly_overspent_total: number
}

export interface AssignApplyResponse {
  to_assign: number
  to_return: number
  categories_changed: number
  tba_after: number
  /** Change-log batch for undo; null when nothing moved. */
  batch_id: string | null
}

export function useAssignStrategyTotals(budgetId: string | null, month: string, enabled: boolean) {
  return useQuery({
    queryKey: [ROOT.assignStrategies, budgetId, month],
    queryFn: () =>
      apiClient
        .get<AssignStrategyTotalsResponse>(`/${budgetId}/assign/strategies`, {
          params: { month },
        })
        .then((r) => r.data),
    enabled: !!budgetId && enabled,
    staleTime: 0,
  })
}

/**
 * `coverIds` (Target Amount only): the envelopes previewed as "Cover +
 * target". Part of the key, so changing a row's choice asks the server for
 * the new figures; the previous answer stays drawn while it does.
 */
export function useAssignPreview(
  budgetId: string | null,
  month: string,
  strategy: AssignStrategy | null,
  coverIds: readonly string[] = []
) {
  const cover_ids = [...coverIds].sort()
  return useQuery({
    queryKey: [ROOT.assignPreview, budgetId, month, strategy, cover_ids],
    queryFn: () =>
      apiClient
        .get<AssignPreviewResponse>(`/${budgetId}/assign/preview`, {
          params: { month, strategy, cover_ids },
          // FastAPI reads a repeated `cover_ids=`, not axios's `cover_ids[]=`.
          paramsSerializer: { indexes: null },
        })
        .then((r) => r.data),
    enabled: !!budgetId && strategy !== null,
    placeholderData: keepPreviousData,
    staleTime: 0,
  })
}

export function useAssignApply(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { month: string; strategy: AssignStrategy; cover_ids?: string[] }) =>
      apiClient.post<AssignApplyResponse>(`/${budgetId}/assign/apply`, data).then((r) => r.data),
    onSuccess: () => void invalidateAfterMoneyMove(qc, budgetId),
  })
}
