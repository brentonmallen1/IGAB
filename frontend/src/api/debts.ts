import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'

export type DebtType =
  | 'mortgage'
  | 'auto'
  | 'student'
  | 'personal'
  | 'credit_card'
  | 'medical'
  | 'other'

export interface Debt {
  id: string
  budget_id: string
  name: string
  debt_type: DebtType
  mode: 'managed' | 'unmanaged'
  linked_account_id: string | null
  linked_category_id: string | null
  current_balance: number
  interest_rate: number
  minimum_payment: number
  compounding: string
  origination_date: string | null
  original_principal: number | null
  baseline_payoff_date: string | null
  baseline_never_pays_off: boolean
  live_payoff_date: string | null
  live_never_pays_off: boolean
  has_live_projection: boolean
  created_at: string
  updated_at: string
}

export interface DebtCreate {
  name: string
  debt_type: DebtType
  interest_rate: number
  minimum_payment: number
  compounding?: string
  linked_account_id?: string | null
  manual_balance?: number | null
  origination_date?: string | null
  original_principal?: number | null
}

export interface AmortizationMonth {
  month_index: number
  date: string
  payment: number
  principal_paid: number
  interest_paid: number
  balance: number
}

export interface BalancePoint {
  date: string
  balance: number
}

export interface AmortizationResponse {
  current_balance: number
  baseline_schedule: AmortizationMonth[]
  baseline_payoff_date: string | null
  baseline_never_pays_off: boolean
  baseline_total_interest: number
  extra_payment: number | null
  extra_schedule: AmortizationMonth[] | null
  extra_payoff_date: string | null
  extra_never_pays_off: boolean
  extra_total_interest: number | null
  live_payoff_date: string | null
  live_never_pays_off: boolean
  live_average_payment: number | null
  history: BalancePoint[]
}

export function useDebts(budgetId: string | null) {
  return useQuery({
    queryKey: ['debts', budgetId],
    queryFn: () => apiClient.get<Debt[]>(`/${budgetId}/debts`).then((r) => r.data),
    enabled: !!budgetId,
    staleTime: 30_000,
  })
}

export function useCreateDebt(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: DebtCreate) =>
      apiClient.post<Debt>(`/${budgetId}/debts`, body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['debts', budgetId] }),
  })
}

export function useUpdateDebt(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ debtId, ...body }: Partial<DebtCreate> & { debtId: string }) =>
      apiClient.patch<Debt>(`/${budgetId}/debts/${debtId}`, body).then((r) => r.data),
    onSuccess: (_, { debtId }) => {
      qc.invalidateQueries({ queryKey: ['debts', budgetId] })
      qc.invalidateQueries({ queryKey: ['debtAmortization', budgetId, debtId] })
    },
  })
}

export function useDeleteDebt(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (debtId: string) => apiClient.delete(`/${budgetId}/debts/${debtId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['debts', budgetId] })
      qc.invalidateQueries({ queryKey: ['categories', budgetId] })
    },
  })
}

export function useCreateDebtSnapshot(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ debtId, balance, date }: { debtId: string; balance: number; date?: string }) =>
      apiClient.post(`/${budgetId}/debts/${debtId}/balance-snapshots`, { balance, date }),
    onSuccess: (_, { debtId }) => {
      qc.invalidateQueries({ queryKey: ['debts', budgetId] })
      qc.invalidateQueries({ queryKey: ['debtAmortization', budgetId, debtId] })
      qc.invalidateQueries({ queryKey: ['netWorth', budgetId] })
    },
  })
}

export function useDebtAmortization(
  budgetId: string | null,
  debtId: string | null,
  options: { extraPayment?: number; fromOrigination?: boolean } = {}
) {
  const { extraPayment = 0, fromOrigination = false } = options
  return useQuery({
    queryKey: ['debtAmortization', budgetId, debtId, extraPayment, fromOrigination],
    queryFn: () =>
      apiClient
        .get<AmortizationResponse>(`/${budgetId}/debts/${debtId}/amortization`, {
          params: {
            ...(extraPayment > 0 ? { extra_payment: extraPayment } : {}),
            ...(fromOrigination ? { from: 'origination' } : {}),
          },
        })
        .then((r) => r.data),
    enabled: !!budgetId && !!debtId,
    staleTime: 30_000,
  })
}

export function useLinkCategoryDebt(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ categoryId, debtId }: { categoryId: string; debtId: string | null }) =>
      apiClient.put(`/${budgetId}/categories/${categoryId}/link-debt`, { debt_id: debtId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['debts', budgetId] })
      qc.invalidateQueries({ queryKey: ['categories', budgetId] })
    },
  })
}
