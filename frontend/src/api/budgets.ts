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

export function useImportYnabAsBudget() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ name, file }: { name: string; file: File }) => {
      const formData = new FormData()
      formData.append('name', name)
      formData.append('file', file)
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
