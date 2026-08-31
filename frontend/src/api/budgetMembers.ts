import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import { ROOT } from './queryKeys'

export interface BudgetMember {
  user_id: string
  email: string
  display_name: string | null
  role: 'owner' | 'member'
}

export function useBudgetMembers(budgetId: string | null) {
  return useQuery({
    queryKey: [ROOT.budgetMembers, budgetId],
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
      qc.invalidateQueries({ queryKey: [ROOT.budgetMembers, budgetId] })
      qc.invalidateQueries({ queryKey: [ROOT.budgets] })
    },
  })
}

export function useRemoveBudgetMember(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (userId: string) => apiClient.delete(`/${budgetId}/members/${userId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [ROOT.budgetMembers, budgetId] })
      qc.invalidateQueries({ queryKey: [ROOT.budgets] })
    },
  })
}
