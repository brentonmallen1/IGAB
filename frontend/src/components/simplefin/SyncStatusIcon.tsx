import { Cloud, CloudOff, CloudAlert, RefreshCw } from 'lucide-react'
import type { Account } from '../../types'
import './SyncStatusIcon.css'

type SyncState = 'fresh' | 'stale' | 'error' | 'broken' | 'syncing' | 'disabled' | 'never'

/**
 * `broken` outranks every age-based state, and is the one this used to miss.
 *
 * A re-linked bank account syncs on schedule, succeeds, and matches nothing —
 * so it stayed `fresh` for nine days while importing none of its
 * transactions. Age says only that the app asked recently, never that the
 * answer was any good.
 */
export function getSyncState(account: Account, isSyncing: boolean, hasFault = false): SyncState {
  if (!account.simplefin_account_id) return 'disabled'
  if (!account.simplefin_sync_enabled) return 'disabled'
  if (isSyncing) return 'syncing'
  if (hasFault) return 'broken'
  if (!account.last_simplefin_sync_at) return 'never'
  const ageMs = Date.now() - new Date(account.last_simplefin_sync_at).getTime()
  const ageHours = ageMs / (1000 * 60 * 60)
  if (ageHours < 4) return 'fresh'
  if (ageHours < 24) return 'stale'
  return 'error'
}

export function formatSyncAge(lastSyncAt: string | null): string {
  if (!lastSyncAt) return 'Never synced'
  const ageMs = Date.now() - new Date(lastSyncAt).getTime()
  const ageMin = Math.floor(ageMs / 60_000)
  if (ageMin < 2) return 'Just synced'
  if (ageMin < 60) return `Synced ${ageMin}m ago`
  const ageH = Math.floor(ageMin / 60)
  if (ageH < 24) return `Synced ${ageH}h ago`
  return `Synced ${Math.floor(ageH / 24)}d ago`
}

interface Props {
  account: Account
  isSyncing?: boolean
  onSyncClick?: (e: React.MouseEvent) => void
  lastSyncError?: string | null
  /** This account's bank link no longer resolves — see `useSyncFaults`. */
  fault?: string | null
}

export function SyncStatusIcon({
  account,
  isSyncing = false,
  onSyncClick,
  lastSyncError,
  fault,
}: Props) {
  if (!account.simplefin_account_id) return null

  const state = getSyncState(account, isSyncing, Boolean(fault))

  const tooltipLines = [
    state === 'disabled'
      ? 'Sync disabled'
      : state === 'never'
        ? 'Never synced — click to sync'
        : state === 'syncing'
          ? 'Syncing…'
          : state === 'broken'
            ? (fault as string)
            : formatSyncAge(account.last_simplefin_sync_at),
    ...(state === 'broken' ? [formatSyncAge(account.last_simplefin_sync_at)] : []),
    ...(lastSyncError && state !== 'broken' ? [`Last error: ${lastSyncError}`] : []),
    ...(state === 'stale' || state === 'error' ? ['Click to sync now'] : []),
  ]

  return (
    <span
      className={`sync-status-icon sync-status-icon--${state}`}
      onClick={onSyncClick}
      role={onSyncClick ? 'button' : undefined}
      tabIndex={onSyncClick ? 0 : undefined}
      title={tooltipLines.join('\n')}
      aria-label={tooltipLines[0]}
    >
      {state === 'syncing' ? (
        <RefreshCw size={12} className="sync-status-icon__spin" />
      ) : state === 'disabled' ? (
        <CloudOff size={12} />
      ) : state === 'fresh' ? (
        <Cloud size={12} />
      ) : (
        <CloudAlert size={12} />
      )}
    </span>
  )
}
