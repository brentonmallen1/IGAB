import { useState } from 'react'
import toast from 'react-hot-toast'
import {
  formatSyncSummary,
  useSimpleFINConnections,
  useSyncAllSimpleFIN,
} from '../api/simplefin'
import { useAppStore } from '../stores/appStore'

/**
 * "Sync every account, now" — one implementation for the three places that
 * offer it (the Accounts page, the sidebar, the command palette).
 *
 * The alternative was the same mutate-then-toast block written three times,
 * which is how the Accounts page came to be the only one that knew about
 * rate limits. `available` is false when no bank is linked, so a trigger can
 * hide itself rather than explain an empty result, and `lastSummary` outlives
 * the toast for the page that prints it beside the button.
 */
export function useSyncAllAccounts() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data: connections = [] } = useSimpleFINConnections()
  const syncAll = useSyncAllSimpleFIN(budgetId)
  const [lastSummary, setLastSummary] = useState<string | null>(null)

  async function run() {
    if (!budgetId || connections.length === 0 || syncAll.isPending) return
    try {
      const result = await syncAll.mutateAsync()
      const failed = result.connections.filter((c) => c.error)
      const summary = formatSyncSummary(result)
      // Every connection refused (rate limit, rotated credentials) is a
      // failure, not a quiet "imported 0".
      if (failed.length === result.connections.length && failed.length > 0) {
        setLastSummary(null)
        toast.error(failed[0].error ?? 'Sync failed')
      } else {
        setLastSummary(summary)
        toast.success(summary)
      }
    } catch {
      setLastSummary(null)
      toast.error('Sync failed — check your connection')
    }
  }

  return {
    syncAll: run,
    isPending: syncAll.isPending,
    available: connections.length > 0,
    lastSummary,
  }
}
