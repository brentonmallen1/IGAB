import { useCallback, useState } from 'react'
import { canCountTowardEmergencyFund } from '../../utils/accountKinds'

interface Flags {
  countsAsSavings: boolean
  countsTowardEmergencyFund: boolean
}

/** What the account modals send for the two savings flags. The emergency-fund
 *  mark goes as false wherever it cannot apply — on budget, a liability, or not
 *  counting as savings — so a form never sends a flag the server refuses. */
export function savingsFlagsPayload(
  flags: Flags,
  account: { onBudget: boolean; classification: 'asset' | 'liability' | null | undefined }
): { counts_as_savings: boolean; counts_toward_emergency_fund: boolean } {
  return {
    counts_as_savings: flags.countsAsSavings,
    counts_toward_emergency_fund:
      flags.countsTowardEmergencyFund &&
      canCountTowardEmergencyFund({
        on_budget: account.onBudget,
        classification: account.classification ?? null,
        counts_as_savings: flags.countsAsSavings,
      }),
  }
}

/** The two savings flags as form state, shared by New Account and account
 *  settings. Turning Counts as savings off clears the emergency-fund mark, so
 *  turning it back on does not quietly restore a choice made before. */
export function useSavingsFlags(initial: Flags) {
  const [countsAsSavings, setSaves] = useState(initial.countsAsSavings)
  const [countsTowardEmergencyFund, setCountsTowardEmergencyFund] = useState(
    initial.countsTowardEmergencyFund
  )
  // Stable, like a useState setter, so an effect can list it.
  const setCountsAsSavings = useCallback((value: boolean) => {
    setSaves(value)
    if (!value) setCountsTowardEmergencyFund(false)
  }, [])
  return {
    countsAsSavings,
    countsTowardEmergencyFund,
    setCountsAsSavings,
    setCountsTowardEmergencyFund,
  }
}
