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
  /** 'manual_fallback' = linked account's register is empty; the pre-link
   * manual balance stands in until an opening balance is added */
  balance_source: 'ledger' | 'manual' | 'manual_fallback'
  /** Null until the terms are filled in — see terms_complete */
  interest_rate: number | null
  minimum_payment: number | null
  /** False = no APR/minimum on file yet, so every projection below is absent
   * rather than zero. The one flag to branch on. */
  terms_complete: boolean
  origination_date: string | null
  original_principal: number | null
  /** This month's interest at the current balance; null without a rate */
  monthly_interest_now: number | null
  /** Average of recent positive payments; null until 2+ months of history.
   * Observed from the ledger, so it survives missing terms. */
  average_recent_payment: number | null
  /** Contractual term implied by origination + principal + minimum payment */
  implied_term_months: number | null
  /** True = the entered minimum couldn't have amortized the original loan
   * (usually the P&I-vs-escrow data-entry trap) */
  implied_never_pays_off: boolean | null
  /** Promotional financing: 0% until this date, interest_rate after */
  promo_end_date: string | null
  /** Deal charges interest retroactively if not cleared by the deadline */
  promo_deferred_interest: boolean
  /** Explicitly known contractual term (overrides the implied estimate) */
  term_months: number | null
  promo_projection: PromoProjection | null
  baseline_payoff_date: string | null
  baseline_never_pays_off: boolean
  live_payoff_date: string | null
  live_never_pays_off: boolean
  has_live_projection: boolean
  created_at: string
  updated_at: string
}

export interface PromoProjection {
  months_until_promo_end: number
  balance_at_promo_end_minimum: number
  balance_at_promo_end_live: number | null
  clears_before_promo: boolean
  /** Estimate of retroactive interest if the deadline is missed */
  deferred_interest_estimate: number | null
}

export interface LiabilityCreate {
  name: string
  liability_type: LiabilityType
  interest_rate: number
  minimum_payment: number
  linked_account_id?: string | null
  manual_balance?: number | null
  origination_date?: string | null
  original_principal?: number | null
  promo_end_date?: string | null
  promo_deferred_interest?: boolean
  term_months?: number | null
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
  /** False = terms not set: an empty schedule and null totals, not an error */
  terms_complete: boolean
  baseline_schedule: AmortizationMonth[]
  baseline_payoff_date: string | null
  baseline_never_pays_off: boolean
  baseline_total_interest: number | null
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
