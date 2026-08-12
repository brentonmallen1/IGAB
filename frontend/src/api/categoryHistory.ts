import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import type { CategoryHistory, AutoAssignAction } from '../types'

export function useCategoryHistory(budgetId: string | null, categoryId: string | null) {
  return useQuery({
    queryKey: ['categoryHistory', budgetId, categoryId],
    queryFn: async () => {
      const { data } = await apiClient.get<CategoryHistory>(
        `/${budgetId}/categories/${categoryId}/history`,
      )
      return data
    },
    enabled: !!budgetId && !!categoryId,
    staleTime: 60_000,
  })
}

export function useCategoryHistoryBatch(budgetId: string | null, categoryIds: string[]) {
  return useQuery({
    queryKey: ['categoryHistoryBatch', budgetId, categoryIds],
    queryFn: async () => {
      const { data } = await apiClient.post<CategoryHistory[]>(
        `/${budgetId}/categories/history/batch`,
        { category_ids: categoryIds },
      )
      return data
    },
    enabled: !!budgetId && categoryIds.length > 0,
    staleTime: 60_000,
  })
}

export function useAutoAssign(budgetId: string, month: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      categoryIds,
      action,
    }: {
      categoryIds: string[]
      action: AutoAssignAction
    }) =>
      apiClient
        .post(`/${budgetId}/categories/auto-assign`, { category_ids: categoryIds, action, month })
        .then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['budgetMonth', budgetId] })
      qc.invalidateQueries({ queryKey: ['categoryHistoryBatch', budgetId] })
    },
  })
}
