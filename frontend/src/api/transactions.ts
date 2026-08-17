import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { apiClient } from './client'
import type {
  BudgetTransactionsResponse,
  BulkActionResult,
  Payee,
  SimilarTransaction,
  SplitCreate,
  Transaction,
  TransactionCreate,
} from '../types'
import type { TransactionFilters } from '../utils/searchParser'
import { hasActiveFilters } from '../utils/searchParser'

/** Surface per-item bulk failures instead of silently half-applying. */
function reportBulkFailures(result: BulkActionResult, actionLabel: string) {
  if (result.failed.length === 0) return
  const first = result.failed[0].reason
  const more = result.failed.length > 1 ? ` (+${result.failed.length - 1} more)` : ''
  toast.error(`${result.failed.length} of ${result.failed.length + result.updated.length} not ${actionLabel}: ${first}${more}`)
}

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
      if (filters.hasAttachment != null) params.has_attachment = filters.hasAttachment
      if (filters.excludeCleared) params.exclude_cleared = filters.excludeCleared
      if (filters.startDate) params.start_date = filters.startDate
      if (filters.endDate) params.end_date = filters.endDate
      if (filters.direction) params.direction = filters.direction
      if (filters.isTransfer != null) params.is_transfer = filters.isTransfer
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

/** All-accounts register: infinite listing across every account in the budget.
 * Same filter semantics and register ordering as the per-account listing. */
export function useInfiniteBudgetTransactions(
  budgetId: string | null,
  filters: TransactionFilters = {},
) {
  const filtered = hasActiveFilters(filters)
  const limit = filtered ? FILTERED_LIMIT : PAGE_SIZE

  return useInfiniteQuery({
    queryKey: ['all-transactions', budgetId, filters],
    queryFn: async ({ pageParam }) => {
      const params: Record<string, unknown> = { limit, offset: pageParam, order: 'register' }
      if (filters.text) params.search = filters.text
      if (filters.cleared) params.cleared = filters.cleared
      if (filters.uncategorized) params.uncategorized = true
      if (filters.unapproved) params.unapproved = true
      if (filters.isOrMode) params.is_or_mode = true
      if (filters.categoryIds?.length) params.category_ids = filters.categoryIds.join(',')
      if (filters.payeeIds?.length) params.payee_ids = filters.payeeIds.join(',')
      if (filters.accountIds?.length) params.account_ids = filters.accountIds.join(',')
      if (filters.amountMin != null) params.amount_min = filters.amountMin
      if (filters.amountMax != null) params.amount_max = filters.amountMax
      if (filters.hasAttachment != null) params.has_attachment = filters.hasAttachment
      if (filters.excludeCleared) params.exclude_cleared = filters.excludeCleared
      if (filters.startDate) params.start_date = filters.startDate
      if (filters.endDate) params.end_date = filters.endDate
      if (filters.direction) params.direction = filters.direction
      if (filters.isTransfer != null) params.is_transfer = filters.isTransfer
      const { data } = await apiClient.get<BudgetTransactionsResponse>(
        `/${budgetId}/transactions`,
        { params },
      )
      return data.transactions
    },
    getNextPageParam: (lastPage, allPages) => {
      if (filtered || lastPage.length < limit) return undefined
      return allPages.flat().length
    },
    initialPageParam: 0,
    enabled: !!budgetId,
    staleTime: 10_000,
  })
}

export interface BudgetTransactionParams {
  startDate: string
  endDate: string
  scope: 'parent' | 'leaf'
  direction?: 'outflow' | 'inflow'
  categoryIds?: string[]
  payeeIds?: string[]
  accountIds?: string[]
  dayOfWeek?: number
  limit?: number
  offset?: number
}

/** Budget-wide listing for report drill-downs. Always posted + cash-flow rows
 * so panel totals reconcile with the report aggregates being drilled into. */
export function useBudgetTransactions(
  budgetId: string | null,
  params: BudgetTransactionParams | null,
) {
  return useQuery({
    queryKey: ['budget-transactions', budgetId, params],
    queryFn: async () => {
      const p: Record<string, unknown> = {
        start_date: params!.startDate,
        end_date: params!.endDate,
        scope: params!.scope,
        posted_only: true,
        cash_flow_only: true,
        limit: params!.limit ?? 200,
        offset: params!.offset ?? 0,
      }
      if (params!.direction) p.direction = params!.direction
      if (params!.dayOfWeek != null) p.day_of_week = params!.dayOfWeek
      if (params!.categoryIds?.length) p.category_ids = params!.categoryIds.join(',')
      if (params!.payeeIds?.length) p.payee_ids = params!.payeeIds.join(',')
      if (params!.accountIds?.length) p.account_ids = params!.accountIds.join(',')
      const { data } = await apiClient.get<BudgetTransactionsResponse>(
        `/${budgetId}/transactions`,
        { params: p },
      )
      return data
    },
    enabled: !!budgetId && !!params,
    staleTime: 30_000,
  })
}

/** Recent transactions for a single category across all accounts, newest first.
 * Pass accountId to narrow to one account. */
export function useCategoryTransactions(
  budgetId: string | null,
  categoryId: string | null,
  limit: number,
  accountId?: string | null,
) {
  return useQuery({
    queryKey: ['category-transactions', budgetId, categoryId, limit, accountId ?? null],
    queryFn: async () => {
      const params: Record<string, unknown> = { category_ids: categoryId, scope: 'leaf', limit }
      if (accountId) params.account_ids = accountId
      const { data } = await apiClient.get<BudgetTransactionsResponse>(
        `/${budgetId}/transactions`,
        { params },
      )
      return data
    },
    enabled: !!budgetId && !!categoryId,
    staleTime: 10_000,
  })
}

/** Recent transactions for a single payee across all accounts, newest first.
 * Used to preview what a payee actually is before merging it away. */
export function usePayeeTransactions(
  budgetId: string | null,
  payeeId: string | null,
  limit: number,
) {
  return useQuery({
    queryKey: ['payee-transactions', budgetId, payeeId, limit],
    queryFn: async () => {
      const { data } = await apiClient.get<BudgetTransactionsResponse>(
        `/${budgetId}/transactions`,
        { params: { payee_ids: payeeId, limit } },
      )
      return data
    },
    enabled: !!budgetId && !!payeeId,
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
      qc.invalidateQueries({ queryKey: ['all-transactions'] })
      qc.invalidateQueries({ queryKey: ['category-transactions', budgetId] })
      qc.invalidateQueries({ queryKey: ['accounts', budgetId] })
      qc.invalidateQueries({ queryKey: ['budgetMonth', budgetId] })
      qc.invalidateQueries({ queryKey: ['pending-review-count'] })
      qc.invalidateQueries({ queryKey: ['pending-review-count-account', txn.account_id] })
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
      qc.invalidateQueries({ queryKey: ['all-transactions'] })
      qc.invalidateQueries({ queryKey: ['category-transactions', budgetId] })
      qc.invalidateQueries({ queryKey: ['accounts', budgetId] })
      qc.invalidateQueries({ queryKey: ['budgetMonth', budgetId] })
      qc.invalidateQueries({ queryKey: ['reconcile-status'] })
      qc.invalidateQueries({ queryKey: ['pending-review-count'] })
      qc.invalidateQueries({ queryKey: ['pending-review-count-account', txn.account_id] })
    },
  })
}

export function useConvertToSplit(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, splits }: { id: string; splits: SplitCreate[] }) =>
      apiClient
        .post<Transaction>(
          `/transactions/${id}/split`,
          { splits },
          { params: { budget_id: budgetId } },
        )
        .then((r) => r.data),
    onSuccess: (txn) => {
      qc.invalidateQueries({ queryKey: ['transactions', txn.account_id] })
      qc.invalidateQueries({ queryKey: ['all-transactions'] })
      qc.invalidateQueries({ queryKey: ['category-transactions', budgetId] })
      qc.invalidateQueries({ queryKey: ['accounts', budgetId] })
      qc.invalidateQueries({ queryKey: ['budgetMonth', budgetId] })
      qc.invalidateQueries({ queryKey: ['pending-review-count'] })
      qc.invalidateQueries({ queryKey: ['pending-review-count-account', txn.account_id] })
    },
  })
}

export function useDeleteTransaction(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, accountId }: { id: string; accountId: string }) => {
      const { data } = await apiClient.delete<{ batch_id: string }>(
        `/transactions/${id}`,
        { params: { budget_id: budgetId } }
      )
      return { accountId, batchId: data.batch_id }
    },
    onSuccess: ({ accountId }) => {
      qc.refetchQueries({ queryKey: ['transactions', accountId] })
      qc.invalidateQueries({ queryKey: ['all-transactions'] })
      qc.invalidateQueries({ queryKey: ['category-transactions', budgetId] })
      qc.invalidateQueries({ queryKey: ['accounts', budgetId] })
      qc.invalidateQueries({ queryKey: ['budgetMonth', budgetId] })
      qc.invalidateQueries({ queryKey: ['pending-review-count'] })
      qc.invalidateQueries({ queryKey: ['pending-review-count-account', accountId] })
    },
  })
}

export function useBulkUpdateCleared(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ transactionIds, cleared, accountId }: { transactionIds: string[]; cleared: string; accountId: string | null }) =>
      apiClient.patch<BulkActionResult>(`/${budgetId}/transactions/bulk-cleared`, {
        transaction_ids: transactionIds,
        cleared,
      }).then((r) => ({ accountId, result: r.data })),
    onSuccess: ({ accountId, result }) => {
      reportBulkFailures(result, 'updated')
      // Null account = all-accounts register: rows span accounts, refresh them all
      qc.invalidateQueries({ queryKey: accountId ? ['transactions', accountId] : ['transactions'] })
      qc.invalidateQueries({ queryKey: ['all-transactions'] })
      qc.invalidateQueries({ queryKey: ['accounts', budgetId] })
      qc.invalidateQueries({ queryKey: ['budgetMonth', budgetId] })
      qc.invalidateQueries({ queryKey: ['reconcile-status'] })
    },
  })
}

export function useBulkCategorize(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ transactionIds, categoryId, accountId }: { transactionIds: string[]; categoryId: string; accountId: string | null }) =>
      apiClient.patch<BulkActionResult>(`/${budgetId}/transactions/bulk-categorize`, {
        transaction_ids: transactionIds,
        category_id: categoryId,
      }).then((r) => ({ accountId, result: r.data })),
    onSuccess: ({ accountId, result }) => {
      reportBulkFailures(result, 'categorized')
      qc.invalidateQueries({ queryKey: accountId ? ['transactions', accountId] : ['transactions'] })
      qc.invalidateQueries({ queryKey: ['all-transactions'] })
      qc.invalidateQueries({ queryKey: ['category-transactions', budgetId] })
      qc.invalidateQueries({ queryKey: ['budgetMonth', budgetId] })
      qc.invalidateQueries({ queryKey: ['pending-review-count'] })
      qc.invalidateQueries({ queryKey: accountId ? ['pending-review-count-account', accountId] : ['pending-review-count-account'] })
    },
  })
}

export function useBulkDeleteTransactions(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ transactionIds, accountId }: { transactionIds: string[]; accountId: string | null }) => {
      const { data } = await apiClient.post<BulkActionResult>(
        `/${budgetId}/transactions/bulk-delete`,
        { transaction_ids: transactionIds }
      )
      return { accountId, result: data }
    },
    onSuccess: ({ accountId, result }) => {
      reportBulkFailures(result, 'deleted')
      qc.refetchQueries({ queryKey: accountId ? ['transactions', accountId] : ['transactions'] })
      qc.invalidateQueries({ queryKey: ['all-transactions'] })
      qc.invalidateQueries({ queryKey: ['category-transactions', budgetId] })
      qc.invalidateQueries({ queryKey: ['accounts', budgetId] })
      qc.invalidateQueries({ queryKey: ['budgetMonth', budgetId] })
      qc.invalidateQueries({ queryKey: ['pending-review-count'] })
      qc.invalidateQueries({ queryKey: accountId ? ['pending-review-count-account', accountId] : ['pending-review-count-account'] })
    },
  })
}

export function useUnreconcileTransaction(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiClient
        .post<Transaction>(`/transactions/${id}/unreconcile`, null, {
          params: { budget_id: budgetId },
        })
        .then((r) => r.data),
    onSuccess: (txn) => {
      qc.invalidateQueries({ queryKey: ['transactions', txn.account_id] })
      qc.invalidateQueries({ queryKey: ['all-transactions'] })
      qc.invalidateQueries({ queryKey: ['reconcile-status'] })
    },
  })
}

export function usePendingReviewCount(budgetId: string | null) {
  return useQuery({
    queryKey: ['pending-review-count', budgetId],
    queryFn: async () => {
      const { data } = await apiClient.get<{
        unapproved_only: number
        uncategorized_only: number
        both: number
        total: number
        unapproved: number
        uncategorized: number
      }>(`/${budgetId}/transactions/pending-review-count`)
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
      const { data } = await apiClient.get<{
        unapproved_only: number
        uncategorized_only: number
        both: number
        total: number
        unapproved: number
        uncategorized: number
      }>(`/accounts/${accountId}/pending-review-count`)
      return data
    },
    enabled: !!accountId,
    staleTime: 15_000,
  })
}

export function useBulkApprove(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ transactionIds, accountId }: { transactionIds: string[]; accountId: string | null }) =>
      apiClient.patch<BulkActionResult>(`/${budgetId}/transactions/bulk-approve`, { transaction_ids: transactionIds })
        .then((r) => ({ accountId, result: r.data })),
    onSuccess: ({ accountId, result }) => {
      reportBulkFailures(result, 'approved')
      qc.invalidateQueries({ queryKey: accountId ? ['transactions', accountId] : ['transactions'] })
      qc.invalidateQueries({ queryKey: ['all-transactions'] })
      qc.invalidateQueries({ queryKey: ['pending-review-count', budgetId] })
      qc.invalidateQueries({ queryKey: accountId ? ['pending-review-count-account', accountId] : ['pending-review-count-account'] })
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
      qc.invalidateQueries({ queryKey: ['all-transactions'] })
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

/** Fetch a single transaction by ID — powers the review handoff when an AI job completes. */
export function useTransaction(transactionId: string | null) {
  return useQuery({
    queryKey: ['transaction', transactionId],
    queryFn: async () => {
      const { data } = await apiClient.get<Transaction>(`/transactions/${transactionId}`)
      return data
    },
    enabled: !!transactionId,
  })
}
