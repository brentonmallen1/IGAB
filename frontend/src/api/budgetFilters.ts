import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import type { BudgetFilter } from '../types'

export function useBudgetFilters(budgetId: string | null) {
  return useQuery({
    queryKey: ['budgetFilters', budgetId],
    queryFn: async () => {
      const { data } = await apiClient.get<BudgetFilter[]>(`/${budgetId}/filters`)
      return data
    },
    enabled: !!budgetId,
    staleTime: 60_000,
  })
}

export function useCreateBudgetFilter(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { name: string; category_ids: string[] }) =>
      apiClient.post<BudgetFilter>(`/${budgetId}/filters`, data).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['budgetFilters', budgetId] })
    },
  })
}

export function useUpdateBudgetFilter(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string; name?: string; category_ids?: string[] }) =>
      apiClient.patch<BudgetFilter>(`/filters/${id}`, data).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['budgetFilters', budgetId] })
    },
  })
}

export function useDeleteBudgetFilter(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiClient.delete(`/filters/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['budgetFilters', budgetId] })
    },
  })
}
