import toast from 'react-hot-toast'
import {
  formatSyncSummary,
  useRefetchSimpleFINAccount,
  useSimpleFINConnections,
} from '../api/simplefin'

/**
 * "Fetch the last 90 days again" for one account — one implementation for
 * the two places that offer it: the account's settings dialog, and the
 * bank line under the account header when a gap has stood still long enough
 * to mean rows never arrived (backend: domain/bank_balance.drift_persists).
 *
 * Safe at any time: rows the register already holds re-stamp or skip, and
 * only what is missing imports. `available` is false when no bank is
 * linked, so a trigger can hide itself rather than do nothing.
 */
export function useRefetchAccountWindow(accountId: string, budgetId: string | null) {
  const { data: connections } = useSimpleFINConnections()
  const connection = connections?.[0] ?? null
  const refetch = useRefetchSimpleFINAccount(accountId, budgetId)

  async function run() {
    if (!connection || refetch.isPending) return
    try {
      const result = await refetch.mutateAsync(connection.id)
      if (result.error) toast.error(result.error)
      else toast.success(formatSyncSummary(result))
    } catch {
      toast.error('Could not reach the bank — try again in a moment')
    }
  }

  return { run, isPending: refetch.isPending, available: connection !== null }
}
