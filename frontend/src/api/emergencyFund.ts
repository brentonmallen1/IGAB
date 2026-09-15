import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import { ROOT } from './queryKeys'
import { invalidateAfterTagChange } from './invalidateAfterTagChange'
import type { EmergencyFund, SavingsMode } from '../types'

/** An account the emergency fund may count: a live, open off-budget asset
 *  (`txn_filters.EMERGENCY_FUND_ACCOUNT_CANDIDATE`). */
export interface FundAccountCandidate {
  id: string
  name: string
  balance: number
  /** False: choosing it also turns Counts as savings on, in the same save. */
  counts_as_savings: boolean
  /** Counted by the fund now. */
  member: boolean
}

/** GET /{budget}/emergency-fund — what the fund counts, and what it could. */
export interface EmergencyFundPicker {
  fund: EmergencyFund
  account_candidates: FundAccountCandidate[]
}

/** The picker's one save (PUT /{budget}/emergency-fund). Envelopes are a diff
 *  against the Emergency fund tag's checklist; accounts are the full set. */
export interface EmergencyFundChoice {
  add_categories: string[]
  remove_categories: string[]
  savings_modes: Record<string, SavingsMode | null>
  account_ids: string[]
  external: {
    declared: boolean
    /** Canonical decimal string, or null for "I have this covered". */
    amount: string | null
    note: string | null
  }
}

export function useEmergencyFund(budgetId: string | null) {
  return useQuery({
    queryKey: [ROOT.emergencyFund, budgetId],
    queryFn: () =>
      apiClient.get<EmergencyFundPicker>(`/${budgetId}/emergency-fund`).then((r) => r.data),
    enabled: !!budgetId,
  })
}

/** One save, one undo: envelopes, modes, accounts and the declared amount. */
export function useSetEmergencyFund(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (choice: EmergencyFundChoice) =>
      apiClient.put<EmergencyFundPicker>(`/${budgetId}/emergency-fund`, choice).then((r) => r.data),
    onSuccess: async (picker) => {
      qc.setQueryData([ROOT.emergencyFund, budgetId], picker)
      // Tags, categories, every report and Guide figure that reads the fund
      // (dashboard, essentials, coverage, savings rate, signals, checkup,
      // sizer) — and the accounts whose flags moved.
      await Promise.all([
        invalidateAfterTagChange(qc, budgetId),
        qc.invalidateQueries({ queryKey: [ROOT.accounts, budgetId] }),
      ])
    },
  })
}
