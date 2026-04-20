import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import type { Payee, Transaction, TransactionCreate } from '../types'

export function useTransactions(accountId: string | null, params?: {
  limit?: number
  offset?: number
  start_date?: string
  end_date?: string
}) {
  return useQuery({
    queryKey: ['transactions', accountId, params],
    queryFn: async () => {
      const { data } = await apiClient.get<Transaction[]>(`/accounts/${accountId}/transactions`, {
        params,
      })
      return data
    },
    enabled: !!accountId,
    staleTime: 10_000,
  })
}

export function useCreateTransaction(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: TransactionCreate) =>
      apiClient.post<Transaction>(`/${budgetId}/transactions`, data).then((r) => r.data),
    onSuccess: (txn) => {
      qc.invalidateQueries({ queryKey: ['transactions', txn.account_id] })
      qc.invalidateQueries({ queryKey: ['accounts', budgetId] })
      qc.invalidateQueries({ queryKey: ['budgetMonth', budgetId] })
    },
  })
}

export function useUpdateTransaction(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...data }: Partial<Transaction> & { id: string }) =>
      apiClient
        .patch<Transaction>(`/transactions/${id}`, data, { params: { budget_id: budgetId } })
        .then((r) => r.data),
    onSuccess: (txn) => {
      qc.invalidateQueries({ queryKey: ['transactions', txn.account_id] })
      qc.invalidateQueries({ queryKey: ['accounts', budgetId] })
      qc.invalidateQueries({ queryKey: ['budgetMonth', budgetId] })
      qc.invalidateQueries({ queryKey: ['reconcile-status'] })
    },
  })
}

export function useDeleteTransaction(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, accountId }: { id: string; accountId: string }) =>
      apiClient
        .delete(`/transactions/${id}`, { params: { budget_id: budgetId } })
        .then(() => accountId),
    onSuccess: (accountId) => {
      qc.invalidateQueries({ queryKey: ['transactions', accountId] })
      qc.invalidateQueries({ queryKey: ['accounts', budgetId] })
      qc.invalidateQueries({ queryKey: ['budgetMonth', budgetId] })
    },
  })
}

export function useBulkUpdateCleared(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ transactionIds, cleared }: { transactionIds: string[]; cleared: string }) =>
      apiClient.patch(`/${budgetId}/transactions/bulk-cleared`, {
        transaction_ids: transactionIds,
        cleared,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['transactions'] })
      qc.invalidateQueries({ queryKey: ['accounts', budgetId] })
      qc.invalidateQueries({ queryKey: ['budgetMonth', budgetId] })
      qc.invalidateQueries({ queryKey: ['reconcile-status'] })
    },
  })
}

export function useBulkCategorize(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ transactionIds, categoryId }: { transactionIds: string[]; categoryId: string }) =>
      apiClient.patch(`/${budgetId}/transactions/bulk-categorize`, {
        transaction_ids: transactionIds,
        category_id: categoryId,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['transactions'] })
      qc.invalidateQueries({ queryKey: ['budgetMonth', budgetId] })
    },
  })
}

export function useBulkDeleteTransactions(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (transactionIds: string[]) =>
      apiClient.post(`/${budgetId}/transactions/bulk-delete`, { transaction_ids: transactionIds }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['transactions'] })
      qc.invalidateQueries({ queryKey: ['accounts', budgetId] })
      qc.invalidateQueries({ queryKey: ['budgetMonth', budgetId] })
    },
  })
}

export function usePayees(budgetId: string | null) {
  return useQuery({
    queryKey: ['payees', budgetId],
    queryFn: async () => {
      const { data } = await apiClient.get<Payee[]>(`/${budgetId}/payees`)
      return data
    },
    enabled: !!budgetId,
    staleTime: 60_000,
  })
}
