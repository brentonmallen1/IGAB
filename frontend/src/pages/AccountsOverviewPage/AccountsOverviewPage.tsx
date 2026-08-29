import { useState } from 'react'
import { AccountHygienePanel } from '../../components/accounts/AccountHygienePanel'
import { useNavigate } from 'react-router-dom'
import { RefreshCw, CloudOff, Plus, Pencil, Trash2, Eye, EyeOff, ArchiveRestore } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAccounts, useDeleteAccount, useUpdateAccount } from '../../api/accounts'
import { useLiabilities } from '../../api/liabilities'
import { confirmAccountDeletion } from '../../utils/confirmAccountDeletion'
import { confirmAsync } from '../../stores/confirmStore'
import { useAccountTypes } from '../../api/accountTypes'
import { accountTypeLabel } from '../../constants/accountTypes'
import {
  orderedOnBudgetKeys,
  partitionAccounts,
} from '../../components/layout/Sidebar/sidebarGroups'
import {
  useSimpleFINConnections,
  useSyncSimpleFIN,
  useSimpleFINRateLimitStatus,
} from '../../api/simplefin'
import { SyncStatusIcon, getSyncState } from '../../components/simplefin/SyncStatusIcon'
import { AddAccountModal } from '../../components/accounts/AddAccountModal'
import { AccountSettingsModal } from '../../components/accounts/AccountSettingsModal'
import { AccountTypesPanel } from '../../components/accounts/AccountTypesPanel'
import { useAppStore } from '../../stores/appStore'
import { useFormatters } from '../../hooks/useFormatters'
import type { Account } from '../../types'
import './AccountsOverviewPage.css'


function formatSyncAge(lastSyncAt: string | null): string {
  if (!lastSyncAt) return 'Never synced'
  const ageMs = Date.now() - new Date(lastSyncAt).getTime()
  const ageMin = Math.floor(ageMs / 60_000)
  if (ageMin < 2) return 'Just synced'
  if (ageMin < 60) return `${ageMin}m ago`
  const ageH = Math.floor(ageMin / 60)
  if (ageH < 24) return `${ageH}h ago`
  return `${Math.floor(ageH / 24)}d ago`
}

function formatReconciled(lastReconciledAt: string | null, formatDate: (date: string) => string): string {
  if (!lastReconciledAt) return 'Never reconciled'
  return `Reconciled ${formatDate(lastReconciledAt.split('T')[0])}`
}

interface AccountRowProps {
  account: Account
  isSyncing: boolean
  onSyncClick: (e: React.MouseEvent) => void
  onEdit: (e: React.MouseEvent) => void
  onDelete: (e: React.MouseEvent) => void
  onReopen: (e: React.MouseEvent) => void
}

function AccountRow({
  account,
  isSyncing,
  onSyncClick,
  onEdit,
  onDelete,
  onReopen,
}: AccountRowProps) {
  const { formatMoney, formatDate } = useFormatters()
  const navigate = useNavigate()
  const state = getSyncState(account, isSyncing)
  const balance = Number(account.balance)
  const cleared = Number(account.cleared_balance)
  const uncleared = Number(account.uncleared_balance)

  return (
    <div
      className={`accounts-overview__row ${account.is_closed ? 'accounts-overview__row--closed' : ''}`}
      onClick={() => navigate(`/accounts/${account.id}`)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && navigate(`/accounts/${account.id}`)}
    >
      <div className="accounts-overview__row-main">
        <div className="accounts-overview__row-name-group">
          <span className="accounts-overview__row-name">{account.name}</span>
          {account.is_closed && <span className="accounts-overview__tag accounts-overview__tag--closed">Closed</span>}
          {account.uncategorized_count > 0 && (
            <span
              className="accounts-overview__uncat-badge"
              title={`${account.uncategorized_count} uncategorized transaction${account.uncategorized_count !== 1 ? 's' : ''}`}
            >
              {account.uncategorized_count}
            </span>
          )}
        </div>

        <div className="accounts-overview__row-meta">
          {account.simplefin_account_id ? (
            <span className={`accounts-overview__sync-info accounts-overview__sync-info--${state}`}>
              <SyncStatusIcon account={account} isSyncing={isSyncing} onSyncClick={onSyncClick} />
              <span>{formatSyncAge(account.last_simplefin_sync_at)}</span>
            </span>
          ) : (
            <span className="accounts-overview__sync-info accounts-overview__sync-info--manual">
              <CloudOff size={12} />
              <span>Manual</span>
            </span>
          )}
          <span className="accounts-overview__separator">·</span>
          <span className="accounts-overview__reconciled">{formatReconciled(account.last_reconciled_at, formatDate)}</span>
        </div>
      </div>

      <div className="accounts-overview__row-right">
        <div className="accounts-overview__row-actions">
          {/* Closed accounts are only visible behind "Show closed"; the way
              back should not require opening the settings modal to find it. */}
          {account.is_closed && (
            <button
              className="accounts-overview__action-btn"
              onClick={onReopen}
              title="Reopen account"
              aria-label="Reopen account"
            >
              <ArchiveRestore size={13} />
            </button>
          )}
          <button
            className="accounts-overview__action-btn"
            onClick={onEdit}
            title="Edit account"
            aria-label="Edit account"
          >
            <Pencil size={13} />
          </button>
          <button
            className="accounts-overview__action-btn accounts-overview__action-btn--danger"
            onClick={onDelete}
            title="Delete account"
            aria-label="Delete account"
          >
            <Trash2 size={13} />
          </button>
        </div>

        <div className="accounts-overview__row-balances">
          <span className={`accounts-overview__balance-main ${balance < 0 ? 'negative' : ''}`}>
            {formatMoney(balance)}
          </span>
          <span className="accounts-overview__balance-detail">
            <span title="Cleared balance">C {formatMoney(cleared)}</span>
            {uncleared !== 0 && (
              <span title="Uncleared balance" className={uncleared < 0 ? 'negative' : 'positive'}>
                {uncleared > 0 ? '+' : ''}{formatMoney(uncleared)}
              </span>
            )}
          </span>
        </div>
      </div>
    </div>
  )
}

export function AccountsOverviewPage() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const [showClosed, setShowClosed] = useState(false)
  const [isAddOpen, setIsAddOpen] = useState(false)
  const [editingAccountId, setEditingAccountId] = useState<string | null>(null)

  // Always fetch closed accounts and filter here. Fetching with
  // `includeClosed: showClosed` made the toggle unreachable: with it off the
  // list could not contain a closed account, so `hasClosedAccounts` was
  // always false and the only control that could turn it on never rendered.
  const { data: allAccounts } = useAccounts(budgetId, { includeClosed: true })
  const accounts = showClosed ? allAccounts : allAccounts?.filter((a) => !a.is_closed)
  const { data: typeRows } = useAccountTypes(budgetId)
  const deleteAccount = useDeleteAccount(budgetId ?? '')
  const updateAccount = useUpdateAccount(budgetId ?? '')
  const { data: liabilities = [] } = useLiabilities(budgetId)

  const { data: connections = [] } = useSimpleFINConnections()
  const primaryConnection = connections[0] ?? null
  const { data: rateLimitStatus } = useSimpleFINRateLimitStatus(primaryConnection?.id ?? null)
  const syncMutation = useSyncSimpleFIN(budgetId)
  const [syncMsg, setSyncMsg] = useState<string | null>(null)

  const syncingAccountId =
    syncMutation.isPending
      ? (syncMutation.variables as { accountSimplefinId?: string })?.accountSimplefinId
      : undefined

  async function handleSyncAll() {
    if (!primaryConnection || !budgetId || syncMutation.isPending) return
    if (rateLimitStatus && !rateLimitStatus.can_sync_global) {
      toast.error(`Daily sync limit reached. Resets at midnight UTC.`)
      return
    }
    setSyncMsg(null)
    try {
      const result = await syncMutation.mutateAsync({ connectionId: primaryConnection.id })
      if (result.error) {
        toast.error(result.error)
        setSyncMsg(null)
      } else {
        const parts = [`Imported ${result.imported}`, `skipped ${result.skipped}`]
        if (result.matched) parts.push(`matched ${result.matched}`)
        if (result.cleared) parts.push(`cleared ${result.cleared}`)
        if (result.review_queued) parts.push(`${result.review_queued} need review`)
        const msg = parts.join(', ')
        setSyncMsg(msg)
        toast.success(msg)
      }
    } catch {
      toast.error('Sync failed — check your connection')
      setSyncMsg(null)
    }
  }

  function handleAccountSync(account: Account, e: React.MouseEvent) {
    e.stopPropagation()
    if (!primaryConnection || !budgetId || !account.simplefin_account_id || syncMutation.isPending) return
    if (rateLimitStatus && !rateLimitStatus.can_sync_account) {
      toast.error('Daily sync limit reached. Resets at midnight UTC.')
      return
    }
    syncMutation.mutate(
      { connectionId: primaryConnection.id, accountSimplefinId: account.simplefin_account_id },
      {
        onSuccess: (result) => {
          if (result.error) {
            toast.error(result.error)
          } else {
            toast.success(
              result.review_queued
                ? `Synced ${account.name} — ${result.review_queued} need review`
                : `Synced ${account.name}`,
            )
          }
        },
        onError: () => toast.error(`Failed to sync ${account.name}`),
      },
    )
  }

  function handleEdit(account: Account, e: React.MouseEvent) {
    e.stopPropagation()
    setEditingAccountId(account.id)
  }

  async function handleReopen(account: Account, e: React.MouseEvent) {
    e.stopPropagation()
    const ok = await confirmAsync({
      title: `Reopen ${account.name}?`,
      message: 'It returns to the sidebar and to every account picker.',
      confirmLabel: 'Reopen account',
    })
    if (!ok) return
    try {
      await updateAccount.mutateAsync({ id: account.id, is_closed: false })
      toast.success(`Reopened ${account.name}`)
    } catch {
      toast.error(`Failed to reopen ${account.name}`)
    }
  }

  async function handleDelete(account: Account, e: React.MouseEvent) {
    e.stopPropagation()
    const choice = await confirmAccountDeletion(account, liabilities)
    if (!choice.proceed) return
    try {
      await deleteAccount.mutateAsync({ accountId: account.id, liability: choice.liability })
      toast.success(
        choice.liability === 'keep' && liabilities.some((l) => l.linked_account_id === account.id)
          ? `Deleted ${account.name} — the debt is still tracked`
          : `Deleted ${account.name}`
      )
    } catch {
      toast.error(`Failed to delete ${account.name}`)
    }
  }

  if (!budgetId) {
    return <div className="accounts-overview__empty">No budget selected.</div>
  }

  const { onBudgetByType, offBudgetAssets, offBudgetLiabilityAccounts } = partitionAccounts(
    accounts ?? []
  )
  const groups: { key: string; label: string; accounts: Account[] }[] = [
    ...orderedOnBudgetKeys(onBudgetByType).map((key) => ({
      key,
      label: accountTypeLabel(key, typeRows),
      accounts: onBudgetByType.get(key) ?? [],
    })),
    { key: '__assets', label: 'Tracking — Assets', accounts: offBudgetAssets },
    { key: '__liabilities', label: 'Tracking — Liabilities', accounts: offBudgetLiabilityAccounts },
  ]
  const hasClosedAccounts = allAccounts?.some((a) => a.is_closed) ?? false

  const hasSyncConnection = !!primaryConnection
  const canSyncAll = hasSyncConnection && !syncMutation.isPending && (rateLimitStatus?.can_sync_global ?? true)

  return (
    <div className="accounts-overview">
      <div className="accounts-overview__header">
        <h1 className="accounts-overview__title">Accounts</h1>
        <div className="accounts-overview__header-actions">
          {syncMsg && <span className="accounts-overview__sync-msg">{syncMsg}</span>}
          {(hasClosedAccounts || showClosed) && (
            <button
              className="accounts-overview__toggle-closed-btn"
              onClick={() => setShowClosed((v) => !v)}
              title={showClosed ? 'Hide closed accounts' : 'Show closed accounts'}
            >
              {showClosed ? <EyeOff size={14} /> : <Eye size={14} />}
              <span>{showClosed ? 'Hide closed' : 'Show closed'}</span>
            </button>
          )}
          {hasSyncConnection && (
            <button
              className={`accounts-overview__sync-all-btn ${syncMutation.isPending && !syncingAccountId ? 'accounts-overview__sync-all-btn--spinning' : ''}`}
              onClick={handleSyncAll}
              disabled={!canSyncAll}
              title={
                rateLimitStatus
                  ? `Sync all accounts · ${rateLimitStatus.global_remaining}/12 remaining`
                  : 'Sync all accounts'
              }
            >
              <RefreshCw size={14} />
              <span>Sync All</span>
              {rateLimitStatus && (
                <span className="accounts-overview__sync-badge">{rateLimitStatus.global_remaining}</span>
              )}
            </button>
          )}
          <button
            className="accounts-overview__add-btn"
            onClick={() => setIsAddOpen(true)}
          >
            <Plus size={14} />
            <span>Add Account</span>
          </button>
        </div>
      </div>

      <AccountHygienePanel budgetId={budgetId} />

      <div className="accounts-overview__groups">
        {groups.map(({ key, label, accounts: typeAccounts }) => {
          if (typeAccounts.length === 0) return null
          return (
            <div key={key} className="accounts-overview__group">
              <div className="accounts-overview__group-label">{label}</div>
              <div className="accounts-overview__group-rows surface">
                {typeAccounts.map((acc) => (
                  <AccountRow
                    key={acc.id}
                    account={acc}
                    isSyncing={syncMutation.isPending && syncingAccountId === acc.simplefin_account_id}
                    onSyncClick={(e) => handleAccountSync(acc, e)}
                    onEdit={(e) => handleEdit(acc, e)}
                    onDelete={(e) => handleDelete(acc, e)}
                    onReopen={(e) => handleReopen(acc, e)}
                  />
                ))}
              </div>
            </div>
          )
        })}
        {accounts?.length === 0 && (
          <div className="accounts-overview__empty-state">
            <p>No accounts yet.</p>
            <button className="accounts-overview__add-btn" onClick={() => setIsAddOpen(true)}>
              <Plus size={14} />
              <span>Add your first account</span>
            </button>
          </div>
        )}
      </div>

      <AccountTypesPanel budgetId={budgetId} />

      {isAddOpen && <AddAccountModal onClose={() => setIsAddOpen(false)} />}
      {editingAccountId && (
        <AccountSettingsModal
          accountId={editingAccountId}
          onClose={() => setEditingAccountId(null)}
        />
      )}
    </div>
  )
}
