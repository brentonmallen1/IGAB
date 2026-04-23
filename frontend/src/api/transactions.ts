import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import type { Payee, SimilarTransaction, Transaction, TransactionCreate } from '../types'
import type { TransactionFilters } from '../utils/searchParser'
import { hasActiveFilters } from '../utils/searchParser'

const PAGE_SIZE = 100
const FILTERED_LIMIT = 2000

export function useInfiniteTransactions(accountId: string | null, filters: TransactionFilters = {}) {
  const filtered = hasActiveFilters(filters)
  const limit = filtered ? FILTERED_LIMIT : PAGE_SIZE

  return useInfiniteQuery({
    queryKey: ['transactions', accountId, filters],
    queryFn: async ({ pageParam }) => {
      const params: Record<string, unknown> = { limit, offset: pageParam }
      if (filters.text) params.search = filters.text
      if (filters.cleared) params.cleared = filters.cleared
      if (filters.uncategorized) params.uncategorized = true
      if (filters.unapproved) params.unapproved = true
      if (filters.isOrMode) params.is_or_mode = true
      if (filters.categoryIds?.length) params.category_ids = filters.categoryIds.join(',')
      if (filters.payeeIds?.length) params.payee_ids = filters.payeeIds.join(',')
      if (filters.amountMin != null) params.amount_min = filters.amountMin
      if (filters.amountMax != null) params.amount_max = filters.amountMax
      const { data } = await apiClient.get<Transaction[]>(`/accounts/${accountId}/transactions`, { params })
      return data
    },
    getNextPageParam: (lastPage, allPages) => {
      if (filtered || lastPage.length < limit) return undefined
      return allPages.flat().length
    },
    initialPageParam: 0,
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

export function usePendingReviewCount(budgetId: string | null) {
  return useQuery({
    queryKey: ['pending-review-count', budgetId],
    queryFn: async () => {
      const { data } = await apiClient.get<{ unapproved: number; uncategorized: number }>(
        `/${budgetId}/transactions/pending-review-count`,
      )
      return data
    },
    enabled: !!budgetId,
    staleTime: 15_000,
  })
}

export function usePendingReviewCountForAccount(accountId: string | null) {
  return useQuery({
    queryKey: ['pending-review-count-account', accountId],
    queryFn: async () => {
      const { data } = await apiClient.get<{ unapproved: number; uncategorized: number }>(
        `/accounts/${accountId}/pending-review-count`,
      )
      return data
    },
    enabled: !!accountId,
    staleTime: 15_000,
  })
}

export function useBulkApprove(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (transactionIds: string[]) =>
      apiClient.patch(`/${budgetId}/transactions/bulk-approve`, { transaction_ids: transactionIds }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['transactions'] })
      qc.invalidateQueries({ queryKey: ['pending-review-count', budgetId] })
      qc.invalidateQueries({ queryKey: ['budgetMonth', budgetId] })
    },
  })
}

export function useMergeTransactions(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ transactionIds, survivorId }: { transactionIds: string[]; survivorId?: string }) =>
      apiClient
        .post<Transaction>(`/${budgetId}/transactions/merge`, {
          transaction_ids: transactionIds,
          survivor_id: survivorId ?? null,
        })
        .then((r) => r.data),
    onSuccess: (txn) => {
      qc.invalidateQueries({ queryKey: ['transactions', txn.account_id] })
      qc.invalidateQueries({ queryKey: ['accounts', budgetId] })
      qc.invalidateQueries({ queryKey: ['budgetMonth', budgetId] })
    },
  })
}

export function useSimilarTransactions(
  accountId: string | null,
  amount: number | null,
  txnDate: string | null,
  excludeId: string | null,
) {
  return useQuery({
    queryKey: ['similar-transactions', accountId, amount, txnDate, excludeId],
    queryFn: async () => {
      const params: Record<string, unknown> = { amount, date: txnDate }
      if (excludeId) params.exclude_id = excludeId
      const { data } = await apiClient.get<SimilarTransaction[]>(
        `/accounts/${accountId}/transactions/similar`,
        { params },
      )
      return data
    },
    enabled: !!accountId && amount !== null && amount !== 0 && !!txnDate,
    staleTime: 30_000,
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
