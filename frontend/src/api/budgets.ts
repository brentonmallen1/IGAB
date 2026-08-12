import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import type { Budget, BudgetMonth } from '../types'
import type { YnabImportResult } from './imports'

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

/** One (category, date, delta) probe for the future-overspend pre-save check.
 * amount_delta is the signed change the save would apply — outflow negative;
 * when editing, the old amount goes in as a positive reversal so only the net
 * change counts. */
export interface OverspendProbe {
  category_id: string
  date: string
  amount_delta: number
}

interface FutureOverspendWarning {
  category_id: string
  category_name: string
  month: string
  available_before: string | number
  available_after: string | number
}

function currentMonthKey(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

/**
 * Pre-save guard: would this transaction push a *future* month's category
 * negative? Current-month overspending is already visible on the budget page;
 * a future month's negative would sit unseen until the user navigates there.
 * Returns true to proceed with the save. Never blocks on a failed check —
 * the warning is an affordance, not an invariant.
 */
export async function confirmFutureOverspend(
  budgetId: string,
  probes: OverspendProbe[],
  formatMoney: (n: number) => string
): Promise<boolean> {
  const items = probes.filter(
    (p) => p.category_id && p.amount_delta !== 0 && p.date.slice(0, 7) > currentMonthKey()
  )
  if (!items.some((p) => p.amount_delta < 0)) return true

  let warnings: FutureOverspendWarning[]
  try {
    const { data } = await apiClient.post<{ warnings: FutureOverspendWarning[] }>(
      `/${budgetId}/months/preview-overspend`,
      { items }
    )
    warnings = data.warnings
  } catch {
    return true
  }
  if (warnings.length === 0) return true

  const lines = warnings.map((w) => {
    const month = new Date(`${w.month}T00:00:00`).toLocaleDateString(undefined, {
      month: 'long',
      year: 'numeric',
    })
    return `• ${w.category_name} in ${month} would drop to ${formatMoney(Number(w.available_after))}`
  })
  return confirm(`This would overspend a future month:\n\n${lines.join('\n')}\n\nSave anyway?`)
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
    onSuccess: () => {
      // Assignments ripple: later months' available and every month's TBA
      // shift, so refresh all cached months, not just the edited one.
      qc.invalidateQueries({ queryKey: ['budgetMonth', budgetId] })
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
      qc.invalidateQueries({ queryKey: ['budgetMonth', budgetId] })
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

export interface SampleBudgetResult {
  budget: Budget
  counts: Record<string, number>
}

/** One-click demo budget with 12 months of curated sample data */
export function useCreateSampleBudget() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      apiClient.post<SampleBudgetResult>('/budgets/create-sample', {}).then((r) => r.data),
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

export interface BudgetUpdate {
  name?: string
  currency_code?: string
  number_format?: string
  date_format?: string
  time_format?: string
}

export function useUpdateBudget() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string } & BudgetUpdate) =>
      apiClient.patch<Budget>(`/budgets/${id}`, data).then((r) => r.data),
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
      qc.invalidateQueries({ queryKey: ['budgetMonth', budgetId] })
      qc.invalidateQueries({ queryKey: ['coverOverspentPreview', budgetId, month] })
      qc.invalidateQueries({ queryKey: ['budgetMoves', budgetId, month] })
      qc.invalidateQueries({ queryKey: ['assignStrategies', budgetId, month] })
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
