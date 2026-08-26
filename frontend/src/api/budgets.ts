import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import { invalidateAfterImport } from './invalidateAfterImport'
import { confirmAsync } from '../stores/confirmStore'
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
  return confirmAsync({
    title: 'Overspend a future month?',
    message: lines.join('\n'),
    confirmLabel: 'Save anyway',
    cancelLabel: 'Go back',
  })
}

export function useSetAssignment(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationKey: ['setAssignment', budgetId],
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
    // Optimistic: the row and month totals update instantly; the server
    // refetch below reconciles cross-month ripple effects.
    onMutate: async ({ categoryId, month, amount }) => {
      await qc.cancelQueries({ queryKey: ['budgetMonth', budgetId, month] })
      const previous = qc.getQueryData<BudgetMonth>(['budgetMonth', budgetId, month])
      if (previous) {
        const existing = previous.category_balances.find((b) => b.category_id === categoryId)
        const delta = amount - Number(existing?.assigned ?? 0)
        const category_balances = existing
          ? previous.category_balances.map((b) =>
              b.category_id === categoryId
                ? { ...b, assigned: amount, available: Number(b.available) + delta }
                : b
            )
          : [
              ...previous.category_balances,
              {
                category_id: categoryId,
                month,
                assigned: amount,
                activity: 0,
                available: amount,
                // The server owns the target verdict and has not answered yet.
                // null hides the pill for one refetch rather than inventing a
                // status here, which is the rule this field exists to enforce.
                target_status: null,
                needed_this_month: null,
              },
            ]
        qc.setQueryData<BudgetMonth>(['budgetMonth', budgetId, month], {
          ...previous,
          total_assigned: Number(previous.total_assigned) + delta,
          to_be_assigned: Number(previous.to_be_assigned) - delta,
          category_balances,
        })
      }
      return { previous }
    },
    onError: (_err, { month }, context) => {
      if (context?.previous) {
        qc.setQueryData(['budgetMonth', budgetId, month], context.previous)
      }
    },
    onSettled: () => {
      // Assignments ripple: later months' available and every month's TBA
      // shift, so refresh all cached months, not just the edited one — but
      // only once the last of rapid sequential edits settles, so an early
      // refetch can't clobber a later edit's optimistic state.
      if (qc.isMutating({ mutationKey: ['setAssignment', budgetId] }) === 1) {
        qc.invalidateQueries({ queryKey: ['budgetMonth', budgetId] })
      }
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

/** Undo one recorded move: assignments step back by its amount and the row
 *  leaves the month's list. Not a reverse move — nothing new is recorded. */
export function useUndoMove(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (move: { id: string; month: string }) =>
      apiClient.post(`/${budgetId}/budget/moves/${move.id}/undo`),
    onSuccess: (_, { month }) => {
      qc.invalidateQueries({ queryKey: ['budgetMonth', budgetId] })
      qc.invalidateQueries({ queryKey: ['budgetMoves', budgetId, month] })
      qc.invalidateQueries({ queryKey: ['assignStrategies', budgetId, month] })
      qc.invalidateQueries({ queryKey: ['changes', budgetId] })
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

/** Seed the cached budgets list with a just-created budget, then refetch.
 * Seeding closes the race where the caller navigates into the new budget
 * while the list refetch is still in flight — MainLayout would read the
 * stale cached list, judge the new id "stale", and bounce back to the
 * selector. Returning the invalidation promise makes mutateAsync wait for
 * the refetch, so navigation always happens against fresh data. */
function seedBudgetsCache(qc: ReturnType<typeof useQueryClient>, budget: Budget) {
  // Seed even when the list was never fetched — `old ? … : old` made this a
  // no-op on a cold cache, and refetchType 'all' reaches the selector's
  // query when it is not mounted at this moment (plain invalidation only
  // refetches active queries, which read as "budget missing until refresh").
  qc.setQueryData<Budget[]>(['budgets'], (old) =>
    old ? [...old.filter((b) => b.id !== budget.id), budget] : [budget]
  )
  return qc.invalidateQueries({ queryKey: ['budgets'], refetchType: 'all' })
}

export function useCreateBudget() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { name: string; currency_code?: string }) =>
      apiClient.post<Budget>('/budgets', data).then((r) => r.data),
    onSuccess: (budget) => seedBudgetsCache(qc, budget),
  })
}

export interface SampleBudgetResult {
  budget: Budget
  counts: Record<string, number>
}

export type SampleTier = 'starter' | 'full'

/** One-click demo budget. 'starter' = the quick 5-account demo; 'full' = a
 * complex dual-income household (~16 accounts, 2½ years) that the starter is
 * a strict subset of. */
export function useCreateSampleBudget() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (tier: SampleTier = 'starter') =>
      apiClient.post<SampleBudgetResult>('/budgets/create-sample', { tier }).then((r) => r.data),
    onSuccess: (result) =>
      // The new budget arrives with accounts, payees and transactions already
      // in it — every cache an import touches, not just the budget list.
      Promise.all([
        seedBudgetsCache(qc, result.budget),
        invalidateAfterImport(qc, result.budget.id),
      ]),
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
    onSuccess: (_, id) => {
      qc.setQueryData<Budget[]>(['budgets'], (old) => old?.filter((b) => b.id !== id))
      return qc.invalidateQueries({ queryKey: ['budgets'] })
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
    }) =>
      apiClient
        .post<{ batch_id: string | null }>(`/${budgetId}/cover-overspent/apply`, data)
        .then((r) => r.data),
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
  /** The account name gave no confident signal, so the suggestion is a
   *  fallback the user should confirm. A tracked account (a house, a vehicle)
   *  left on budget by mistake corrupts every budget total. */
  needs_review: boolean
  /** Sum of the account's register rows — the fastest way for a user to tell
   *  a house from its mortgage. Serialized as a decimal string. */
  implied_balance: string
  /** Oldest and newest register dates (ISO), or null for an empty account.
   *  A YNAB export carries no closed-account marker, so this is the only
   *  signal that an account has been dormant for years. */
  first_activity: string | null
  last_activity: string | null
  /** Accounts sharing a leading name fragment — an institution's accounts, or
   *  something you own and the debt against it. A prompt to compare, never a
   *  merge suggestion: measured on a real export, fuzzy similarity scores 100
   *  for "Redwood" vs "Redwood CC", which are different accounts. */
  related_group: string | null
}

export interface YnabPreviewResult {
  accounts: YnabAccountPreview[]
  transaction_count: number
  budget_entry_count: number
}

export interface YnabAccountTypeChoice {
  account_type: string
  on_budget: boolean
  /** Leave this account (and all its transactions) out of the import —
   * YNAB exports include archived accounts with no marker. */
  skip?: boolean
  /** Import everything, then close the account. Prefer this to `skip` for a
   * dormant account: it keeps the history (so net worth over time stays
   * whole and transfers still pair up) and only hides the account from
   * pickers and report filters. */
  close?: boolean
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
    onSuccess: (result) =>
      // The new budget arrives with accounts, payees and transactions already
      // in it — every cache an import touches, not just the budget list.
      Promise.all([
        seedBudgetsCache(qc, result.budget),
        invalidateAfterImport(qc, result.budget.id),
      ]),
  })
}
