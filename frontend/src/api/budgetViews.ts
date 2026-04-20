import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import type { BudgetView } from '../types'

export function useBudgetViews(budgetId: string | null) {
  return useQuery({
    queryKey: ['budgetViews', budgetId],
    queryFn: async () => {
      const { data } = await apiClient.get<BudgetView[]>(`/${budgetId}/views`)
      return data
    },
    enabled: !!budgetId,
    staleTime: 60_000,
  })
}

export function useCreateBudgetView(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { name: string; category_ids: string[] }) =>
      apiClient.post<BudgetView>(`/${budgetId}/views`, data).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['budgetViews', budgetId] })
    },
  })
}

export function useUpdateBudgetView(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string; name?: string; category_ids?: string[] }) =>
      apiClient.patch<BudgetView>(`/views/${id}`, data).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['budgetViews', budgetId] })
    },
  })
}

export function useDeleteBudgetView(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiClient.delete(`/views/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['budgetViews', budgetId] })
    },
  })
}
