import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import type { Transaction } from '../types'
import { invalidateAfterTransactionChange } from './invalidateAfterTransactionChange'
import { ROOT } from './queryKeys'

export interface ReconciliationStatus {
  cleared_balance: number
  uncleared_count: number
  pending_count: number
  /** Cleared rows a pending duplicate review holds beside the bank's copy —
   * counted twice in `cleared_balance` until the review is settled. Served:
   * the home is `ReconciliationService.get_status` (txn_filters
   * IN_REVIEW_CLEARED), and finish and the adjustment 409 while it is above 0. */
  in_review_count: number
}

export interface ReconciliationSnapshot {
  id: string
  account_id: string
  reconciled_at: string
  statement_balance: number
  cleared_balance: number
  adjustment_amount: number
  note: string | null
}

export function useReconciliationStatus(
  accountId: string | null,
  options?: { refetchInterval?: number }
) {
  return useQuery({
    queryKey: [ROOT.reconcileStatus, accountId],
    queryFn: async () => {
      const { data } = await apiClient.get<ReconciliationStatus>(
        `/accounts/${accountId}/reconcile/status`
      )
      return data
    },
    enabled: !!accountId,
    staleTime: 10_000,
    refetchInterval: options?.refetchInterval,
  })
}

export function useCreateAdjustment(budgetId: string | null, accountId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (adjustmentAmount: number) =>
      apiClient
        .post<Transaction>(`/accounts/${accountId}/reconcile/adjustment`, {
          adjustment_amount: adjustmentAmount,
        })
        .then((r) => r.data),
    onSuccess: () => void invalidateAfterTransactionChange(qc, { budgetId, accountId }),
  })
}

interface FinishReconciliationParams {
  statement_balance: number
  adjustment_transaction_id?: string | null
}

/**
 * Finishing writes transactions: it locks the cleared rows and approves the
 * ones still awaiting approval. So it invalidates what any transaction write
 * does — this hook and the adjustment each kept a three-key list of their
 * own, which knew nothing of the review counts, and the sidebar badge went
 * on counting rows the reconcile had just approved.
 */
export function useFinishReconciliation(budgetId: string | null, accountId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (params: FinishReconciliationParams) =>
      apiClient
        .post<ReconciliationSnapshot>(`/accounts/${accountId}/reconcile/finish`, params)
        .then((r) => r.data),
    onSuccess: () => void invalidateAfterTransactionChange(qc, { budgetId, accountId }),
  })
}

export function useReconciliationHistory(accountId: string | null) {
  return useQuery({
    queryKey: [ROOT.reconcileHistory, accountId],
    queryFn: async () => {
      const { data } = await apiClient.get<ReconciliationSnapshot[]>(
        `/accounts/${accountId}/reconcile/history`
      )
      return data
    },
    enabled: !!accountId,
    staleTime: 60_000,
  })
}
