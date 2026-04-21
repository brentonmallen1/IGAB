import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import type { ScheduledTransaction } from '../types'

export interface ScheduledTransactionCreate {
  account_id: string
  amount: number
  frequency: string
  start_date: string
  payee_id?: string
  category_id?: string
  memo?: string
  end_date?: string
  auto_create?: boolean
  days_before_reminder?: number
}

export function useScheduledTransactions(budgetId: string | null) {
  return useQuery({
    queryKey: ['scheduled-transactions', budgetId],
    queryFn: async () => {
      const { data } = await apiClient.get<ScheduledTransaction[]>(
        `/${budgetId}/scheduled-transactions`,
      )
      return data
    },
    enabled: !!budgetId,
    staleTime: 30_000,
  })
}

export function useScheduledTransactionsByAccount(budgetId: string | null, accountId: string | null) {
  const query = useScheduledTransactions(budgetId)
  return {
    ...query,
    data: query.data?.filter((s) => s.account_id === accountId) ?? [],
  }
}

export function useCreateScheduledTransaction(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: ScheduledTransactionCreate) =>
      apiClient
        .post<ScheduledTransaction>(`/${budgetId}/scheduled-transactions`, body)
        .then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scheduled-transactions', budgetId] }),
  })
}

export function useUpdateScheduledTransaction(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...data }: Partial<ScheduledTransactionCreate> & { id: string }) =>
      apiClient
        .patch<ScheduledTransaction>(`/scheduled-transactions/${id}`, data)
        .then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scheduled-transactions', budgetId] }),
  })
}

export function useDeleteScheduledTransaction(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiClient.delete(`/scheduled-transactions/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scheduled-transactions', budgetId] }),
  })
}

export function useSkipScheduledTransaction(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiClient
        .post<ScheduledTransaction>(`/scheduled-transactions/${id}/skip`, {})
        .then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scheduled-transactions', budgetId] }),
  })
}

export function useEnterScheduledTransaction(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiClient.post(`/scheduled-transactions/${id}/enter`, {}, { params: { budget_id: budgetId } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['scheduled-transactions', budgetId] })
      qc.invalidateQueries({ queryKey: ['transactions'] })
    },
  })
}
