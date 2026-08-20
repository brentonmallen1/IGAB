import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'

export interface BudgetMember {
  user_id: string
  email: string
  display_name: string | null
  role: 'owner' | 'member'
}

export function useBudgetMembers(budgetId: string | null) {
  return useQuery({
    queryKey: ['budget-members', budgetId],
    queryFn: async () => {
      const { data } = await apiClient.get<BudgetMember[]>(`/${budgetId}/members`)
      return data
    },
    enabled: !!budgetId,
  })
}

export function useAddBudgetMember(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (userId: string) =>
      apiClient.post<BudgetMember>(`/${budgetId}/members`, { user_id: userId }).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['budget-members', budgetId] })
      qc.invalidateQueries({ queryKey: ['budgets'] })
    },
  })
}

export function useRemoveBudgetMember(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (userId: string) => apiClient.delete(`/${budgetId}/members/${userId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['budget-members', budgetId] })
      qc.invalidateQueries({ queryKey: ['budgets'] })
    },
  })
}
