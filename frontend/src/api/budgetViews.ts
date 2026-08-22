import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import type { BudgetView } from '../types'

const key = (budgetId: string | null) => ['budgetViews', budgetId]

export function useBudgetViews(budgetId: string | null) {
  return useQuery({
    queryKey: key(budgetId),
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
    mutationFn: (data: { name: string; groups?: string[]; hide_unassigned?: boolean }) =>
      apiClient.post<BudgetView>(`/${budgetId}/views`, data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: key(budgetId) }),
  })
}

export function useUpdateBudgetView(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      ...data
    }: {
      id: string
      name?: string
      hide_unassigned?: boolean
      groups?: string[]
      /** `group_name` resolves against the groups saved in the same request,
       *  so new groups and their contents go up together. */
      placements?: {
        category_id: string
        group_id?: string | null
        group_name?: string | null
        sort_order?: number
        is_hidden?: boolean
      }[]
    }) => apiClient.patch<BudgetView>(`/views/${id}`, data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: key(budgetId) }),
  })
}

export function useDeleteBudgetView(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiClient.delete(`/views/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: key(budgetId) }),
  })
}
