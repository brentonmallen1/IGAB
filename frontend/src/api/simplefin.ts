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
import { ROOT } from './queryKeys'

/**
 * Whether the server can run bank sync. Asked before the setup form is shown:
 * a SimpleFIN setup token is single-use, so a misconfigured server has to say
 * so before the user spends one on it.
 */
export function useSimpleFINConfig() {
  return useQuery({
    queryKey: [ROOT.simplefinConfig],
    queryFn: async () => {
      const { data } = await apiClient.get<SimpleFINConfig>('/simplefin/config')
      return data
    },
    staleTime: 60_000,
  })
}

export function useSimpleFINConnections() {
  return useQuery({
    queryKey: [ROOT.simplefinConnections],
    queryFn: async () => {
      const { data } = await apiClient.get<SimpleFINConnection[]>('/simplefin/connections')
      return data
    },
    staleTime: 30_000,
  })
}

export function useSimpleFINRateLimitStatus(connectionId: string | null) {
  return useQuery({
    queryKey: [ROOT.simplefinRateLimit, connectionId],
    queryFn: async () => {
      const { data } = await apiClient.get<SimpleFINRateLimitStatus>(
        `/simplefin/connections/${connectionId}/status`
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
      apiClient.post<SimpleFINConnection>('/simplefin/setup', { setup_token }).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [ROOT.simplefinConnections] })
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
      qc.invalidateQueries({ queryKey: [ROOT.simplefinConnections] })
    },
  })
}

export function useDeleteSimpleFINConnection() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiClient.delete(`/simplefin/connections/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [ROOT.simplefinConnections] })
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
          }
        )
        .then((r) => r.data),
    onSuccess: () => {
      // A sync is an import: rows, payees it created, balances, budget math,
      // hygiene — the shared sweep covers what per-key lists kept missing
      // (new payees rendered "—" until their staleTime lapsed).
      invalidateAfterImport(qc, budgetId)
      qc.invalidateQueries({ queryKey: [ROOT.simplefinConnections] })
      qc.invalidateQueries({ queryKey: [ROOT.simplefinRateLimit] })
      qc.invalidateQueries({ queryKey: [ROOT.simplefinMatches] })
    },
  })
}

/** An account whose bank link the feed no longer offers. */
export interface OrphanedLink {
  account_id: string
  account_name: string
  stored_simplefin_id: string
  suggested_feed_id: string | null
  suggested_feed_name: string | null
}

/** One entry from the bridge's `errlist`. `con.auth` means re-authentication. */
export interface BankError {
  code: string
  message: string
  connection_id: string | null
}

export interface ConnectionSyncOutcome {
  connection_id: string
  imported: number
  skipped: number
  adopted: number
  error: string | null
  orphaned_links: OrphanedLink[]
  bank_errors: BankError[]
}

export interface SyncAllResult {
  imported: number
  skipped: number
  /** Why rows were skipped, keyed by `SkipReason`. See formatSyncSummary. */
  skip_reasons?: Record<string, number>
  matched: number
  adopted: number
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
      qc.invalidateQueries({ queryKey: [ROOT.simplefinConnections] })
      qc.invalidateQueries({ queryKey: [ROOT.simplefinRateLimit] })
      qc.invalidateQueries({ queryKey: [ROOT.simplefinMatches] })
    },
  })
}

/**
 * One sentence for what a sync did, so the three places that can start one
 * cannot describe the same run differently.
 *
 * A broken bank link leads, because it is the only outcome here the user can
 * act on and the only one that means an account has silently stopped
 * importing. This message used to read "Imported 0, skipped 586" for exactly
 * that situation — indistinguishable from a quiet morning with nothing new,
 * which is how it went unnoticed for nine days.
 *
 * Errors are counted rather than listed: with several connections the message
 * has to stay a line long, and the connection carries its own error for the
 * settings page to show in full.
 */
export function formatSyncSummary(result: SyncAllResult): string {
  const orphans = result.connections.flatMap((c) => c.orphaned_links ?? [])
  if (orphans.length > 0) {
    const names = orphans.map((o) => o.account_name)
    const who = names.length === 1 ? names[0] : `${names.length} accounts`
    return `${who} no longer match an account at the bank — relink to resume importing`
  }

  const needsAuth = result.connections
    .flatMap((c) => c.bank_errors ?? [])
    .filter((e) => e.code === 'con.auth')
  if (needsAuth.length > 0 && result.imported === 0) {
    const who = needsAuth.length === 1 ? 'A bank' : `${needsAuth.length} banks`
    return `${who} needs re-authenticating — see SimpleFIN in Settings`
  }

  const failed = result.connections.filter((c) => c.error).length
  const parts = [`Imported ${result.imported}`]
  if (result.adopted) parts.push(`re-linked ${result.adopted} existing`)
  if (result.matched) parts.push(`matched ${result.matched}`)
  if (result.cleared) parts.push(`cleared ${result.cleared}`)
  if (result.review_queued) parts.push(`${result.review_queued} need review`)
  // "Nothing new" is the honest reading when every skip was a row already
  // filed, and it is what the benign case actually means.
  parts.push(describeSkips(result))
  const summary = parts.filter(Boolean).join(', ')
  if (failed === 0) return summary
  const banks = failed === 1 ? '1 connection' : `${failed} connections`
  return `${summary} — ${banks} could not sync`
}

/** The `skipped` half of the summary, in the terms the count actually means. */
function describeSkips(result: SyncAllResult): string {
  if (result.skipped === 0) return ''
  const reasons = result.skip_reasons ?? {}
  const onlyAlreadyFiled =
    Object.keys(reasons).length > 0 && Object.keys(reasons).every((r) => r === 'already_posted')
  if (onlyAlreadyFiled) return `${result.skipped} already filed`
  const foreign = reasons.foreign_account ?? 0
  if (foreign === result.skipped && foreign > 0) {
    return `${foreign} belong to unlinked accounts`
  }
  return `skipped ${result.skipped}`
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
      qc.invalidateQueries({ queryKey: [ROOT.accounts] })
    },
  })
}

export function useUnlinkSimpleFINAccount(accountId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiClient.delete(`/accounts/${accountId}/link-simplefin`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [ROOT.accounts] })
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
      qc.invalidateQueries({ queryKey: [ROOT.accounts] })
    },
  })
}

export function useSimpleFINRemoteAccounts(connectionId: string | null) {
  return useQuery({
    queryKey: [ROOT.simplefinRemoteAccounts, connectionId],
    queryFn: async () => {
      const { data } = await apiClient.get<{ id: string; name: string }[]>(
        `/simplefin/connections/${connectionId}/accounts`
      )
      return data
    },
    enabled: !!connectionId,
    staleTime: 60_000,
  })
}

export function usePendingMatchesForAccount(accountId: string | null) {
  return useQuery({
    queryKey: [ROOT.pendingMatchesAccount, accountId],
    queryFn: async () => {
      const { data } = await apiClient.get<TransactionMatch[]>(
        `/accounts/${accountId}/pending-matches`
      )
      return data
    },
    enabled: !!accountId,
    staleTime: 15_000,
  })
}

export function usePendingMatches(budgetId: string | null) {
  return useQuery({
    queryKey: [ROOT.simplefinMatches, budgetId],
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
    mutationFn: (matchId: string) => apiClient.post(`/simplefin/matches/${matchId}/accept`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [ROOT.simplefinMatches] })
      qc.invalidateQueries({ queryKey: [ROOT.pendingMatchesAccount, accountId] })
      qc.invalidateQueries({ queryKey: [ROOT.transactions] })
      qc.invalidateQueries({ queryKey: [ROOT.allTransactions] })
      // Accepting merges away the duplicate — cleared/working balances change
      qc.invalidateQueries({ queryKey: [ROOT.accounts] })
      qc.invalidateQueries({ queryKey: [ROOT.pendingReviewCount] })
      qc.invalidateQueries({ queryKey: [ROOT.pendingReviewCountAccount] })
    },
  })
}

export function useRejectMatch(accountId?: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (matchId: string) => apiClient.post(`/simplefin/matches/${matchId}/reject`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [ROOT.simplefinMatches] })
      qc.invalidateQueries({ queryKey: [ROOT.pendingMatchesAccount, accountId] })
    },
  })
}
