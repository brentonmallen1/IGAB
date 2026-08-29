import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import { invalidateAfterImport } from './invalidateAfterImport'
import type {
  SimpleFINConfig,
  SimpleFINConnection,
  SimpleFINRateLimitStatus,
  SyncResult,
  TransactionMatch,
} from '../types'

/**
 * Whether the server can run bank sync. Asked before the setup form is shown:
 * a SimpleFIN setup token is single-use, so a misconfigured server has to say
 * so before the user spends one on it.
 */
export function useSimpleFINConfig() {
  return useQuery({
    queryKey: ['simplefin-config'],
    queryFn: async () => {
      const { data } = await apiClient.get<SimpleFINConfig>('/simplefin/config')
      return data
    },
    staleTime: 60_000,
  })
}

export function useSimpleFINConnections() {
  return useQuery({
    queryKey: ['simplefin-connections'],
    queryFn: async () => {
      const { data } = await apiClient.get<SimpleFINConnection[]>('/simplefin/connections')
      return data
    },
    staleTime: 30_000,
  })
}

export function useSimpleFINRateLimitStatus(connectionId: string | null) {
  return useQuery({
    queryKey: ['simplefin-rate-limit', connectionId],
    queryFn: async () => {
      const { data } = await apiClient.get<SimpleFINRateLimitStatus>(
        `/simplefin/connections/${connectionId}/status`,
      )
      return data
    },
    enabled: !!connectionId,
    staleTime: 0,
    refetchOnMount: 'always',
    refetchInterval: 30_000,
  })
}

export function useSetupSimpleFIN() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (setup_token: string) =>
      apiClient
        .post<SimpleFINConnection>('/simplefin/setup', { setup_token })
        .then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['simplefin-connections'] })
    },
  })
}

export function useUpdateSimpleFINConnection() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      ...updates
    }: {
      id: string
      sync_enabled?: boolean
      /** Omit to leave the schedule alone; [] turns it off. */
      sync_hours?: number[]
    }) =>
      apiClient
        .put<SimpleFINConnection>(`/simplefin/connections/${id}`, updates)
        .then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['simplefin-connections'] })
    },
  })
}

export function useDeleteSimpleFINConnection() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiClient.delete(`/simplefin/connections/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['simplefin-connections'] })
    },
  })
}

export function useSyncSimpleFIN(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      connectionId,
      accountSimplefinId,
    }: {
      connectionId: string
      accountSimplefinId?: string
    }) =>
      apiClient
        .post<SyncResult>(
          `/simplefin/connections/${connectionId}/sync`,
          {},
          {
            params: {
              budget_id: budgetId,
              ...(accountSimplefinId ? { account_simplefin_id: accountSimplefinId } : {}),
            },
          },
        )
        .then((r) => r.data),
    onSuccess: () => {
      // A sync is an import: rows, payees it created, balances, budget math,
      // hygiene — the shared sweep covers what per-key lists kept missing
      // (new payees rendered "—" until their staleTime lapsed).
      invalidateAfterImport(qc, budgetId)
      qc.invalidateQueries({ queryKey: ['simplefin-connections'] })
      qc.invalidateQueries({ queryKey: ['simplefin-rate-limit'] })
      qc.invalidateQueries({ queryKey: ['simplefin-matches'] })
    },
  })
}

export interface ConnectionSyncOutcome {
  connection_id: string
  imported: number
  skipped: number
  error: string | null
}

export interface SyncAllResult {
  imported: number
  skipped: number
  matched: number
  review_queued: number
  cleared: number
  removed_pending: number
  connections: ConnectionSyncOutcome[]
}

/**
 * Sync every connection, not just the first one.
 *
 * The Accounts page's "Sync All" posted to `connections[0]`, so a household
 * with two banks only ever synced one of them from it. The loop lives on the
 * server, where the rate limit and the connection list already are, and this
 * is what the Accounts page, the sidebar and the command palette all call.
 */
export function useSyncAllSimpleFIN(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.post<SyncAllResult>(`/${budgetId}/simplefin/sync-all`)
      return data
    },
    onSuccess: () => {
      // A sync is an import — same sweep the single-connection sync uses.
      invalidateAfterImport(qc, budgetId)
      qc.invalidateQueries({ queryKey: ['simplefin-connections'] })
      qc.invalidateQueries({ queryKey: ['simplefin-rate-limit'] })
      qc.invalidateQueries({ queryKey: ['simplefin-matches'] })
    },
  })
}

/**
 * One sentence for what a sync did, so the three places that can start one
 * cannot describe the same run differently.
 *
 * Errors are counted rather than listed: with several connections the message
 * has to stay a line long, and the connection carries its own error for the
 * settings page to show in full.
 */
export function formatSyncSummary(result: SyncAllResult): string {
  const failed = result.connections.filter((c) => c.error).length
  const parts = [`Imported ${result.imported}`, `skipped ${result.skipped}`]
  if (result.matched) parts.push(`matched ${result.matched}`)
  if (result.cleared) parts.push(`cleared ${result.cleared}`)
  if (result.review_queued) parts.push(`${result.review_queued} need review`)
  const summary = parts.join(', ')
  if (failed === 0) return summary
  const banks = failed === 1 ? '1 connection' : `${failed} connections`
  return `${summary} — ${banks} could not sync`
}

export function useLinkSimpleFINAccount(accountId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name: string | null }) =>
      apiClient.post(`/accounts/${accountId}/link-simplefin`, {
        simplefin_account_id: id,
        simplefin_account_name: name,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['accounts'] })
    },
  })
}

export function useUnlinkSimpleFINAccount(accountId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiClient.delete(`/accounts/${accountId}/link-simplefin`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['accounts'] })
    },
  })
}

export function useUpdateAccountSimpleFINSettings(accountId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (simplefin_sync_enabled: boolean) =>
      apiClient.patch(`/accounts/${accountId}/simplefin-settings`, null, {
        params: { simplefin_sync_enabled },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['accounts'] })
    },
  })
}

export function useSimpleFINRemoteAccounts(connectionId: string | null) {
  return useQuery({
    queryKey: ['simplefin-remote-accounts', connectionId],
    queryFn: async () => {
      const { data } = await apiClient.get<{ id: string; name: string }[]>(
        `/simplefin/connections/${connectionId}/accounts`,
      )
      return data
    },
    enabled: !!connectionId,
    staleTime: 60_000,
  })
}

export function usePendingMatchesForAccount(accountId: string | null) {
  return useQuery({
    queryKey: ['pending-matches-account', accountId],
    queryFn: async () => {
      const { data } = await apiClient.get<TransactionMatch[]>(
        `/accounts/${accountId}/pending-matches`,
      )
      return data
    },
    enabled: !!accountId,
    staleTime: 15_000,
  })
}

export function usePendingMatches(budgetId: string | null) {
  return useQuery({
    queryKey: ['simplefin-matches', budgetId],
    queryFn: async () => {
      const { data } = await apiClient.get<TransactionMatch[]>('/simplefin/matches', {
        params: { budget_id: budgetId },
      })
      return data
    },
    enabled: !!budgetId,
    staleTime: 15_000,
  })
}

export function useAcceptMatch(accountId?: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (matchId: string) =>
      apiClient.post(`/simplefin/matches/${matchId}/accept`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['simplefin-matches'] })
      qc.invalidateQueries({ queryKey: ['pending-matches-account', accountId] })
      qc.invalidateQueries({ queryKey: ['transactions'] })
      qc.invalidateQueries({ queryKey: ['all-transactions'] })
      // Accepting merges away the duplicate — cleared/working balances change
      qc.invalidateQueries({ queryKey: ['accounts'] })
      qc.invalidateQueries({ queryKey: ['pending-review-count'] })
      qc.invalidateQueries({ queryKey: ['pending-review-count-account'] })
    },
  })
}

export function useRejectMatch(accountId?: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (matchId: string) =>
      apiClient.post(`/simplefin/matches/${matchId}/reject`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['simplefin-matches'] })
      qc.invalidateQueries({ queryKey: ['pending-matches-account', accountId] })
    },
  })
}
