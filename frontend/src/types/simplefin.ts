/**
 * Bank-sync (SimpleFIN) shapes, split out of `types/index.ts` to keep it
 * inside the file-length budget. `index.ts` re-exports this module, so
 * everything still imports from `'../types'`.
 */

export interface SimpleFINConnection {
  id: string
  user_id: string
  last_sync_at: string | null
  sync_enabled: boolean
  /** UTC hours (0-23) this connection syncs itself at; [] is never. The
   *  server owns the schedule — see db/models.SimpleFINConnection.sync_hours
   *  — and validates the count against its own daily rate limit. */
  sync_hours: number[]
  global_requests_today: number
  account_requests_today: number
  last_sync_error: string | null
  last_sync_error_at: string | null
  created_at: string
  updated_at: string
}

/**
 * Served by GET /simplefin/config. The client cannot decide any of this: the
 * encryption key is server-side env, so the server is the only one that knows
 * whether bank sync can store credentials at all.
 * Home: backend/src/igab/integrations/simplefin/encryption.py
 */
export interface SimpleFINConfig {
  configured: boolean
  /** Null when configured; otherwise what is wrong, in the user's words. */
  problem: string | null
  /** The one command that produces an acceptable key — served, not duplicated here. */
  generate_key_command: string
}

export interface SimpleFINRateLimitStatus {
  global_used: number
  global_remaining: number
  /** The day's budget for all-accounts requests. Served, not written here —
   *  home: backend/src/igab/integrations/simplefin/limits.py. */
  global_limit: number
  account_used: number
  account_remaining: number
  /** The day's budget for single-account requests. Same home. */
  account_limit: number
  can_sync_global: boolean
  can_sync_account: boolean
  resets_at: string
}

export interface SyncResult {
  imported: number
  skipped: number
  skip_reasons?: Record<string, number>
  matched: number
  adopted: number
  review_queued: number
  cleared: number
  removed_pending: number
  /** Rows the bank no longer reports that the run kept. See api/simplefin.ts. */
  kept_unreported: number
  /** See api/simplefin.ts for the shapes; typed there so the summary formatter
   *  can read a single-connection result and a sync-all the same way. */
  orphaned_links: import('../api/simplefin').OrphanedLink[]
  bank_errors: import('../api/simplefin').BankError[]
  balance_drift: import('../api/simplefin').BalanceDrift[]
  /** Opening balances the run declined to write. See api/simplefin.ts. */
  refused_anchors?: string[]
  /** First syncs that wrote no opening balance because the account already
   *  had history. Informational. See api/simplefin.ts. */
  anchors_skipped_for_history?: string[]
  error: string | null
  global_used: number | null
  global_remaining: number | null
  account_used: number | null
  account_remaining: number | null
}

export interface TransactionMatch {
  id: string
  synced_transaction_id: string
  manual_transaction_id: string
  confidence_score: number
  status: 'pending' | 'accepted' | 'rejected'
  created_at: string
}
