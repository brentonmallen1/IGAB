import toast from 'react-hot-toast'
import {
  formatSyncSummary,
  usePrimaryConnection,
  useRefetchSimpleFINAccount,
} from '../api/simplefin'

/** What a trigger needs from the hook: the action, and whether it is running. */
export interface RefetchHandle {
  run: () => void
  isPending: boolean
}

/** The trigger's label, one wording for every place that offers it. */
export function refetchLabel(isPending: boolean): string {
  return isPending ? 'Fetching…' : 'Fetch the last 90 days again'
}

/**
 * "Fetch the last 90 days again" for one account — one implementation for
 * the two places that offer it: the account's settings dialog, and the
 * bank line under the account header when a gap has stood still long enough
 * to mean rows never arrived (backend: domain/bank_balance.drift_persists).
 *
 * Safe at any time: rows the register already holds re-stamp or skip, and
 * only what is missing imports. `available` is false when no bank is linked
 * or there is no account yet, so a trigger can hide itself rather than do
 * nothing.
 */
export function useRefetchAccountWindow(
  accountId: string | null | undefined,
  budgetId: string | null
) {
  const connection = usePrimaryConnection()
  const refetch = useRefetchSimpleFINAccount(accountId ?? null, budgetId)
  const available = connection !== null && Boolean(accountId)

  async function run() {
    if (!available || !connection || refetch.isPending) return
    try {
      const result = await refetch.mutateAsync(connection.id)
      if (result.error) toast.error(result.error)
      else toast.success(formatSyncSummary(result))
    } catch {
      toast.error('Could not reach the bank — try again in a moment')
    }
  }

  const handle: RefetchHandle = { run: () => void run(), isPending: refetch.isPending }
  return { ...handle, available }
}
