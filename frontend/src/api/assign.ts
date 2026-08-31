import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import type { AssignStrategy } from '../types'
import { ROOT } from './queryKeys'

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
  total_overspent: number
  /** The part of `total_overspent` Cover Overspending would actually fund;
   *  the rest rode onto a card and no assignment retires it. The dropdown row
   *  reads this so its number matches the dialog it opens. */
  total_overspent_cash: number
  strategies: AssignStrategyTotal[]
}

export interface AssignPreviewItem {
  category_id: string
  category_name: string
  current_assigned: number
  delta: number
  new_assigned: number
}

export interface AssignPreviewResponse {
  strategy: AssignStrategy
  items: AssignPreviewItem[]
  total_needed: number | null
  to_assign: number
  to_return: number
  tba_before: number
  tba_after: number
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

export function useAssignPreview(
  budgetId: string | null,
  month: string,
  strategy: AssignStrategy | null
) {
  return useQuery({
    queryKey: [ROOT.assignPreview, budgetId, month, strategy],
    queryFn: () =>
      apiClient
        .get<AssignPreviewResponse>(`/${budgetId}/assign/preview`, {
          params: { month, strategy },
        })
        .then((r) => r.data),
    enabled: !!budgetId && strategy !== null,
    staleTime: 0,
  })
}

export function useAssignApply(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { month: string; strategy: AssignStrategy }) =>
      apiClient.post<AssignApplyResponse>(`/${budgetId}/assign/apply`, data).then((r) => r.data),
    onSuccess: (_, { month }) => {
      qc.invalidateQueries({ queryKey: [ROOT.budgetMonth, budgetId] })
      qc.invalidateQueries({ queryKey: [ROOT.budgetMoves, budgetId, month] })
      qc.invalidateQueries({ queryKey: [ROOT.assignStrategies, budgetId, month] })
      qc.invalidateQueries({ queryKey: [ROOT.assignPreview, budgetId, month] })
      qc.invalidateQueries({ queryKey: [ROOT.categoryHistoryBatch, budgetId] })
      qc.invalidateQueries({ queryKey: [ROOT.coverOverspentPreview, budgetId, month] })
    },
  })
}
