import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'

export type LiabilityType =
  | 'mortgage'
  | 'auto'
  | 'student'
  | 'personal'
  | 'credit_card'
  | 'medical'
  | 'other'

export interface Liability {
  id: string
  budget_id: string
  name: string
  liability_type: LiabilityType
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

export interface LiabilityCreate {
  name: string
  liability_type: LiabilityType
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

export function useLiabilities(budgetId: string | null) {
  return useQuery({
    queryKey: ['liabilities', budgetId],
    queryFn: () => apiClient.get<Liability[]>(`/${budgetId}/liabilities`).then((r) => r.data),
    enabled: !!budgetId,
    staleTime: 30_000,
  })
}

export function useCreateLiability(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: LiabilityCreate) =>
      apiClient.post<Liability>(`/${budgetId}/liabilities`, body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['liabilities', budgetId] }),
  })
}

export function useUpdateLiability(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ liabilityId, ...body }: Partial<LiabilityCreate> & { liabilityId: string }) =>
      apiClient
        .patch<Liability>(`/${budgetId}/liabilities/${liabilityId}`, body)
        .then((r) => r.data),
    onSuccess: (_, { liabilityId }) => {
      qc.invalidateQueries({ queryKey: ['liabilities', budgetId] })
      qc.invalidateQueries({ queryKey: ['liabilityAmortization', budgetId, liabilityId] })
    },
  })
}

export function useDeleteLiability(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (liabilityId: string) =>
      apiClient.delete(`/${budgetId}/liabilities/${liabilityId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['liabilities', budgetId] })
      qc.invalidateQueries({ queryKey: ['categories', budgetId] })
    },
  })
}

export function useCreateLiabilitySnapshot(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      liabilityId,
      balance,
      date,
    }: {
      liabilityId: string
      balance: number
      date?: string
    }) =>
      apiClient.post(`/${budgetId}/liabilities/${liabilityId}/balance-snapshots`, {
        balance,
        date,
      }),
    onSuccess: (_, { liabilityId }) => {
      qc.invalidateQueries({ queryKey: ['liabilities', budgetId] })
      qc.invalidateQueries({ queryKey: ['liabilityAmortization', budgetId, liabilityId] })
      qc.invalidateQueries({ queryKey: ['netWorth', budgetId] })
    },
  })
}

export function useLiabilityAmortization(
  budgetId: string | null,
  liabilityId: string | null,
  options: { extraPayment?: number; fromOrigination?: boolean } = {}
) {
  const { extraPayment = 0, fromOrigination = false } = options
  return useQuery({
    queryKey: ['liabilityAmortization', budgetId, liabilityId, extraPayment, fromOrigination],
    queryFn: () =>
      apiClient
        .get<AmortizationResponse>(`/${budgetId}/liabilities/${liabilityId}/amortization`, {
          params: {
            ...(extraPayment > 0 ? { extra_payment: extraPayment } : {}),
            ...(fromOrigination ? { from: 'origination' } : {}),
          },
        })
        .then((r) => r.data),
    enabled: !!budgetId && !!liabilityId,
    staleTime: 30_000,
  })
}

export function useLinkCategoryLiability(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      categoryId,
      liabilityId,
    }: {
      categoryId: string
      liabilityId: string | null
    }) =>
      apiClient.put(`/${budgetId}/categories/${categoryId}/link-liability`, {
        liability_id: liabilityId,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['liabilities', budgetId] })
      qc.invalidateQueries({ queryKey: ['categories', budgetId] })
    },
  })
}
