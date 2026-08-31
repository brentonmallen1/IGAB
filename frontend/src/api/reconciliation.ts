import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import type { Transaction } from '../types'
import { ROOT } from './queryKeys'

export interface ReconciliationStatus {
  cleared_balance: number
  uncleared_count: number
  pending_count: number
}

export interface ReconciliationSnapshot {
  id: string
  account_id: string
  reconciled_at: string
  statement_balance: string
  cleared_balance: string
  adjustment_amount: string
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

export function useCreateAdjustment(accountId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (adjustmentAmount: number) =>
      apiClient
        .post<Transaction>(`/accounts/${accountId}/reconcile/adjustment`, {
          adjustment_amount: adjustmentAmount,
        })
        .then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [ROOT.transactions] })
      qc.invalidateQueries({ queryKey: [ROOT.accounts] })
      qc.invalidateQueries({ queryKey: [ROOT.reconcileStatus, accountId] })
    },
  })
}

interface FinishReconciliationParams {
  statement_balance: number
  adjustment_transaction_id?: string | null
}

export function useFinishReconciliation(accountId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (params: FinishReconciliationParams) =>
      apiClient
        .post<ReconciliationSnapshot>(`/accounts/${accountId}/reconcile/finish`, params)
        .then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [ROOT.transactions] })
      qc.invalidateQueries({ queryKey: [ROOT.accounts] })
      qc.invalidateQueries({ queryKey: [ROOT.reconcileStatus, accountId] })
    },
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
