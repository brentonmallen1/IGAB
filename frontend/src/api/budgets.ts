import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import type { Budget, BudgetMonth } from '../types'
import type { YnabImportResult } from './imports'

export interface FillTargetsPreviewItem {
  category_id: string
  category_name: string
  current_assigned: number
  proposed_addition: number
  new_assigned: number
}

export interface FillTargetsPreviewResponse {
  items: FillTargetsPreviewItem[]
  total_addition: number
  tba_before: number
  tba_after: number
}

export interface YnabImportBudgetResult {
  budget: Budget
  import_result: YnabImportResult
}

const MULTIPART_HEADERS = { 'Content-Type': undefined }

export async function fetchBudgets(): Promise<Budget[]> {
  const { data } = await apiClient.get<Budget[]>('/budgets')
  return data
}

export async function fetchBudgetMonth(budgetId: string, month: string): Promise<BudgetMonth> {
  const { data } = await apiClient.get<BudgetMonth>(`/${budgetId}/months/${month}`)
  return data
}

export function useBudgets() {
  return useQuery({
    queryKey: ['budgets'],
    queryFn: fetchBudgets,
    staleTime: 60_000,
  })
}

export function useBudgetMonth(budgetId: string | null, month: string) {
  return useQuery({
    queryKey: ['budgetMonth', budgetId, month],
    queryFn: () => fetchBudgetMonth(budgetId!, month),
    enabled: !!budgetId,
    staleTime: 10_000,
  })
}

export function useSetAssignment(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      categoryId,
      month,
      amount,
    }: {
      categoryId: string
      month: string
      amount: number
    }) =>
      apiClient.patch(`/categories/${categoryId}/assignment`, { amount }, {
        params: { month, budget_id: budgetId },
      }),
    onSuccess: (_, { month }) => {
      qc.invalidateQueries({ queryKey: ['budgetMonth', budgetId, month] })
    },
  })
}

export interface BudgetMove {
  id: string
  month: string
  from_category_id: string | null
  to_category_id: string | null
  amount: string
  created_at: string
}

/** Move money between envelopes; a null side means To-Be-Assigned */
export function useMoveMoney(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: {
      from_category_id: string | null
      to_category_id: string | null
      amount: number
      month: string
    }) => apiClient.post(`/${budgetId}/budget/move-money`, data),
    onSuccess: (_, { month }) => {
      qc.invalidateQueries({ queryKey: ['budgetMonth', budgetId, month] })
      qc.invalidateQueries({ queryKey: ['budgetMoves', budgetId, month] })
    },
  })
}

export function useMoveHistory(budgetId: string, month: string, enabled: boolean) {
  return useQuery({
    queryKey: ['budgetMoves', budgetId, month],
    queryFn: () =>
      apiClient
        .get<BudgetMove[]>(`/${budgetId}/budget/moves`, { params: { month } })
        .then((r) => r.data),
    enabled,
    staleTime: 10_000,
  })
}

export function useCreateBudget() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { name: string; currency_code?: string }) =>
      apiClient.post<Budget>('/budgets', data).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['budgets'] })
    },
  })
}

export function useRenameBudget() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      apiClient.patch<Budget>(`/budgets/${id}`, { name }).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['budgets'] }),
  })
}

export function useDeleteBudget() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiClient.delete(`/budgets/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['budgets'] }),
  })
}

export function useFillTargetsPreview(budgetId: string | null, month: string, enabled: boolean) {
  return useQuery({
    queryKey: ['fillTargetsPreview', budgetId, month],
    queryFn: () =>
      apiClient
        .get<FillTargetsPreviewResponse>(`/${budgetId}/auto-assign/preview`, { params: { month } })
        .then((r) => r.data),
    enabled: !!budgetId && enabled,
    staleTime: 0,
  })
}

export function useFillTargetsApply(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { month: string; items: FillTargetsPreviewItem[] }) =>
      apiClient.post(`/${budgetId}/auto-assign/apply`, data),
    onSuccess: (_, { month }) => {
      qc.invalidateQueries({ queryKey: ['budgetMonth', budgetId, month] })
      qc.invalidateQueries({ queryKey: ['fillTargetsPreview', budgetId, month] })
    },
  })
}

export interface CoverOverspentPreviewItem {
  category_id: string
  category_name: string
  overspent: number
  proposed_addition: number
  remaining_after: number
}

export interface CoverOverspentPreviewResponse {
  items: CoverOverspentPreviewItem[]
  total_overspent: number
  total_addition: number
  tba_before: number
  tba_after: number
}

export function useCoverOverspentPreview(budgetId: string | null, month: string, enabled: boolean) {
  return useQuery({
    queryKey: ['coverOverspentPreview', budgetId, month],
    queryFn: () =>
      apiClient
        .get<CoverOverspentPreviewResponse>(`/${budgetId}/cover-overspent/preview`, {
          params: { month },
        })
        .then((r) => r.data),
    enabled: !!budgetId && enabled,
    staleTime: 0,
  })
}

export function useCoverOverspentApply(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    // proposed_addition is echoed back verbatim (Decimal-as-string) so the
    // backend re-parses the exact preview amount
    mutationFn: (data: {
      month: string
      items: { category_id: string; proposed_addition: number }[]
    }) => apiClient.post(`/${budgetId}/cover-overspent/apply`, data),
    onSuccess: (_, { month }) => {
      qc.invalidateQueries({ queryKey: ['budgetMonth', budgetId, month] })
      qc.invalidateQueries({ queryKey: ['coverOverspentPreview', budgetId, month] })
      qc.invalidateQueries({ queryKey: ['budgetMoves', budgetId, month] })
      qc.invalidateQueries({ queryKey: ['fillTargetsPreview', budgetId, month] })
    },
  })
}

export interface YnabAccountPreview {
  name: string
  transaction_count: number
  suggested_type: string
  suggested_on_budget: boolean
}

export interface YnabPreviewResult {
  accounts: YnabAccountPreview[]
  transaction_count: number
  budget_entry_count: number
}

export interface YnabAccountTypeChoice {
  account_type: string
  on_budget: boolean
}

/** Parse the export without importing — feeds the account-type mapping step */
export function usePreviewYnabImport() {
  return useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      return apiClient
        .post<YnabPreviewResult>('/budgets/import-ynab/preview', formData, {
          headers: MULTIPART_HEADERS,
        })
        .then((r) => r.data)
    },
  })
}

export function useImportYnabAsBudget() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      name,
      file,
      accountTypes,
    }: {
      name: string
      file: File
      accountTypes?: Record<string, YnabAccountTypeChoice>
    }) => {
      const formData = new FormData()
      formData.append('name', name)
      formData.append('file', file)
      if (accountTypes && Object.keys(accountTypes).length > 0) {
        formData.append('account_types', JSON.stringify(accountTypes))
      }
      return apiClient
        .post<YnabImportBudgetResult>('/budgets/import-ynab', formData, {
          headers: MULTIPART_HEADERS,
        })
        .then((r) => r.data)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['budgets'] })
    },
  })
}
