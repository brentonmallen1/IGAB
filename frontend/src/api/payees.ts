import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import type { Payee } from '../types'

export interface PayeeWithCount extends Payee {
  transaction_count: number
}

export function usePayees(budgetId: string | null) {
  return useQuery({
    queryKey: ['payees', budgetId],
    queryFn: async () => {
      const { data } = await apiClient.get<PayeeWithCount[]>(`/${budgetId}/payees`)
      return data
    },
    enabled: !!budgetId,
    staleTime: 60_000,
  })
}

export function useUpdatePayee(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; name?: string; default_category_id?: string }) =>
      apiClient.patch<Payee>(`/payees/${id}`, body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['payees', budgetId] }),
  })
}

export function useDeletePayee(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiClient.delete(`/payees/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['payees', budgetId] })
      qc.invalidateQueries({ queryKey: ['transactions'] })
    },
  })
}

export function useMergePayee(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ sourceId, targetId }: { sourceId: string; targetId: string }) =>
      apiClient.post(`/payees/${sourceId}/merge`, { target_id: targetId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['payees', budgetId] })
      qc.invalidateQueries({ queryKey: ['transactions'] })
    },
  })
}
