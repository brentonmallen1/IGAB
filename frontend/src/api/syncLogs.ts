/**
 * The bank-sync log, and the health check that badges the nav.
 *
 * Exists because nothing recorded a sync before: `last_sync_at` plus an error
 * field that a successful run cleared meant a sync importing none of an
 * account's transactions left the same trace as one that worked.
 */
import { useQuery } from '@tanstack/react-query'

import { apiClient } from './client'
import { ROOT } from './queryKeys'
import type { BankError, OrphanedLink } from './simplefin'

export interface SyncRunAccount {
  account_id: string | null
  account_name: string | null
  simplefin_account_id: string | null
  /** Zero, on an account the run was told to sync, means the link is broken. */
  feed_txn_count: number
  feed_oldest_date: string | null
  /** The field worth the whole table: how recent the bank's newest row is. */
  feed_newest_date: string | null
  imported: number
  adopted: number
  reidentified: boolean
  orphaned: boolean
}

export interface SyncRun {
  id: string
  connection_id: string | null
  trigger: string
  /** ok | error | rate_limited | degraded */
  status: string
  window_start: string | null
  window_end: string | null
  duration_ms: number | null
  error: string | null
  bank_errors: BankError[]
  orphaned_links: OrphanedLink[]
  feed_txn_count: number
  imported: number
  skipped: number
  skip_reasons: Record<string, number>
  matched: number
  adopted: number
  cleared: number
  review_queued: number
  removed_pending: number
  anchored: number
  created_at: string
}

export interface SyncRunDetail extends SyncRun {
  accounts: SyncRunAccount[]
}

export interface SyncHealth {
  orphaned_links: OrphanedLink[]
  needs_auth: BankError[]
  last_run_at: string | null
}

export function useSyncRuns(budgetId: string | null, opts: { limit?: number } = {}) {
  return useQuery({
    queryKey: [ROOT.syncRuns, budgetId, opts],
    queryFn: async () => {
      const { data } = await apiClient.get<{ runs: SyncRun[]; total_count: number }>(
        `/${budgetId}/simplefin/sync-runs`,
        { params: { limit: opts.limit ?? 50 } }
      )
      return data
    },
    enabled: !!budgetId,
  })
}

/** Fetched only when a row is expanded — the list stays cheap. */
export function useSyncRun(budgetId: string | null, runId: string | null) {
  return useQuery({
    queryKey: [ROOT.syncRun, budgetId, runId],
    queryFn: async () => {
      const { data } = await apiClient.get<SyncRunDetail>(
        `/${budgetId}/simplefin/sync-runs/${runId}`
      )
      return data
    },
    enabled: !!budgetId && !!runId,
  })
}

/**
 * What badges the nav. Reads the latest run only, so a fault clears the badge
 * as soon as a clean sync follows it — a badge that outlives its cause is one
 * people learn to ignore.
 */
export function useSyncHealth(budgetId: string | null) {
  return useQuery({
    queryKey: [ROOT.syncHealth, budgetId],
    queryFn: async () => {
      const { data } = await apiClient.get<SyncHealth>(`/${budgetId}/simplefin/sync-runs/health`)
      return data
    },
    enabled: !!budgetId,
  })
}

export function hasSyncFault(health: SyncHealth | undefined): boolean {
  if (!health) return false
  return health.orphaned_links.length > 0 || health.needs_auth.length > 0
}
