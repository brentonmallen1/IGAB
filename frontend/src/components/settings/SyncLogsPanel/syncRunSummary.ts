/**
 * How one sync run reads, in words.
 *
 * Pure and separate from the panel so every branch is a one-line test. The
 * whole reason this feature exists is that a run's outcome was unreadable:
 * "0 imported, 500+ skipped" described both a broken bank link and a quiet
 * morning with nothing new.
 */
import { describeDrift } from '../../../api/simplefin'
import type { SyncRun, SyncRunAccount } from '../../../api/syncLogs'

/** Names for `domain.enums.SkipReason`, in the terms a person would use. */
const SKIP_LABELS: Record<string, string> = {
  foreign_account: 'belonged to an account this budget does not sync',
  account_not_found: 'named an account that could not be found',
  no_matcher: 'needed review, but no matcher was configured',
  review_import_duplicate: 'were already queued for review',
  already_posted: 'were already filed, and unchanged',
  duplicate_sync_id: 'were already in the register under the same bank id',
}

export function describeSkipReason(reason: string): string {
  return SKIP_LABELS[reason] ?? reason.replace(/_/g, ' ')
}

export type RunVerdict = 'broken' | 'failed' | 'limited' | 'quiet' | 'worked'

/**
 * What a run amounts to. `broken` outranks everything: a run that succeeded
 * while an account matched nothing is the failure this log was built for, and
 * it is the one a status of "ok" used to hide.
 */
export function runVerdict(run: SyncRun): RunVerdict {
  if (run.orphaned_links.length > 0 || run.status === 'degraded') return 'broken'
  if (run.balance_drift.length > 0) return 'broken'
  if (run.status === 'error') return 'failed'
  if (run.status === 'rate_limited') return 'limited'
  if (run.imported === 0 && run.adopted === 0 && run.matched === 0) return 'quiet'
  return 'worked'
}

export function runHeadline(run: SyncRun): string {
  if (run.orphaned_links.length > 0) {
    const names = run.orphaned_links.map((o) => o.account_name)
    return names.length === 1
      ? `${names[0]} no longer matches an account at the bank`
      : `${names.length} accounts no longer match an account at the bank`
  }
  if (run.balance_drift.length > 0) return describeDrift(run.balance_drift)
  if (run.error) return run.error
  const parts: string[] = []
  if (run.imported) parts.push(`${run.imported} imported`)
  if (run.adopted) parts.push(`${run.adopted} re-linked`)
  if (run.matched) parts.push(`${run.matched} matched`)
  if (run.cleared) parts.push(`${run.cleared} cleared`)
  if (run.review_queued) parts.push(`${run.review_queued} to review`)
  if (parts.length === 0) return 'Nothing new'
  return parts.join(', ')
}

/**
 * The window the bridge was asked for, as a sentence: "Sep 11 → now (6 days)".
 * The start date is the part that matters — a gap in the register is a run
 * whose window began after the rows were posted, and only the date says so.
 */
export function describeWindow(run: SyncRun): string | null {
  const days = windowDays(run)
  if (days == null || !run.window_start) return null
  const fmt = (iso: string) =>
    new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  const end = run.window_end ? fmt(run.window_end) : 'now'
  return `${fmt(run.window_start)} → ${end} (${days} day${days === 1 ? '' : 's'})`
}

/** How wide a window the bridge was asked for — over 90 days is capped. */
export function windowDays(run: SyncRun): number | null {
  if (!run.window_start) return null
  const end = run.window_end ? new Date(run.window_end) : new Date(run.created_at)
  const ms = end.getTime() - new Date(run.window_start).getTime()
  return Math.max(0, Math.round(ms / 86_400_000))
}

/**
 * Why one account's row matters. An account the run was told to sync that the
 * feed offered nothing for is the orphaned-link signature — and it is what no
 * count of imported or skipped rows could say.
 */
export function accountNote(account: SyncRunAccount): string | null {
  if (account.orphaned) return 'The bank no longer offers this account — relink it'
  if (account.feed_txn_count === 0) return 'The bank returned nothing for this account'
  if (account.reidentified) return 'The bank reissued every id; existing rows adopted them'
  return null
}
