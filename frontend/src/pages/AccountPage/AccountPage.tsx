import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Settings } from 'lucide-react'
import toast from 'react-hot-toast'
import { TransactionTable } from '../../components/transactions/TransactionTable/TransactionTable'
import { ReconcileBanner } from '../../components/accounts/ReconcileBanner'
import { PendingReviewBanner } from '../../components/accounts/PendingReviewBanner'
import { AccountSettingsModal } from '../../components/accounts/AccountSettingsModal'
import { MatchReviewModal } from '../../components/simplefin/MatchReviewModal'
import { formatSyncAge } from '../../components/simplefin/SyncStatusIcon'
import { useAccounts } from '../../api/accounts'
import {
  useSimpleFINConnections,
  useSyncSimpleFIN,
  usePendingMatches,
} from '../../api/simplefin'
import { useAppStore } from '../../stores/appStore'
import { useUIStore } from '../../stores/uiStore'
import { useFormatters } from '../../hooks/useFormatters'
import './AccountPage.css'

export function AccountPage() {
  const { formatMoney } = useFormatters()
  const { accountId } = useParams<{ accountId: string }>()
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const setSelectedAccount = useAppStore((s) => s.setSelectedAccountId)
  const { data: accounts } = useAccounts(budgetId)

  const account = accounts?.find((a) => a.id === accountId)
  const { isReconciling, reconcileAccountId, startReconciliation, setTransactionSearch } = useUIStore()
  const { data: sfConnections } = useSimpleFINConnections()
  const firstConnection = sfConnections?.[0] ?? null
  const sync = useSyncSimpleFIN(budgetId)
  const [syncMsg, setSyncMsg] = useState<string | null>(null)
  const { isAccountEditorOpen, editingAccountId, openAccountEditor, closeAccountEditor } = useUIStore()
  const { data: pendingMatches = [] } = usePendingMatches(budgetId)
  const [showMatchModal, setShowMatchModal] = useState(false)

  const showReconcileBanner = isReconciling && reconcileAccountId === accountId

  useEffect(() => {
    if (accountId) setSelectedAccount(accountId)
    return () => setSelectedAccount(null)
  }, [accountId, setSelectedAccount])

  async function handleSync() {
    if (!firstConnection || !account?.simplefin_account_id) return
    setSyncMsg(null)
    try {
      const result = await sync.mutateAsync({
        connectionId: firstConnection.id,
        accountSimplefinId: account.simplefin_account_id,
      })
      if (result.error) {
        toast.error(result.error)
        setSyncMsg(null)
      } else {
        const parts = [`Imported ${result.imported}`, `skipped ${result.skipped}`]
        if (result.cleared) parts.push(`cleared ${result.cleared}`)
        const msg = parts.join(', ')
        setSyncMsg(msg)
        toast.success(msg)
      }
    } catch {
      toast.error('Sync failed — check your connection')
      setSyncMsg(null)
    }
  }

  if (!budgetId || !accountId) {
    return <div className="account-page__not-found">No account selected.</div>
  }

  if (!account) {
    return (
      <div className="account-page">
        <div className="account-page__not-found">Loading account…</div>
      </div>
    )
  }

  const balanceClass = Number(account.balance) < 0 ? 'negative' : 'positive'

  return (
    <div className="account-page">
      <div className="account-page__header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div className="account-page__name">{account.name}</div>
          <button
            className="account-page__sync-btn"
            onClick={() => startReconciliation(accountId!)}
            disabled={isReconciling && reconcileAccountId === accountId}
          >
            Reconcile
          </button>
          <button
            className="account-page__settings-btn"
            onClick={() => openAccountEditor(accountId!)}
            aria-label="Account settings"
            title="Account settings"
          >
            <Settings size={14} />
          </button>
          {account.simplefin_account_id && account.simplefin_sync_enabled && (
            <div className="account-page__sync-strip">
              <span className="account-page__sync-age">
                {formatSyncAge(account.last_simplefin_sync_at ?? null)}
              </span>
              <button
                className="account-page__sync-btn"
                onClick={handleSync}
                disabled={sync.isPending || !firstConnection}
              >
                {sync.isPending ? 'Syncing…' : 'Sync Now'}
              </button>
              {syncMsg && <span className="account-page__sync-msg">{syncMsg}</span>}
            </div>
          )}
        </div>
        <div className="account-page__meta">
          <div className="account-page__balance-item">
            <span className="account-page__balance-label">Cleared</span>
            <span className={`account-page__balance-value ${Number(account.cleared_balance) < 0 ? 'negative' : ''}`}>
              {formatMoney(Number(account.cleared_balance))}
            </span>
          </div>
          <div className="account-page__balance-item">
            <span className="account-page__balance-label">Uncleared</span>
            <span className="account-page__balance-value">
              {formatMoney(Number(account.uncleared_balance))}
            </span>
          </div>
          <div className="account-page__balance-item">
            <span className="account-page__balance-label">Working Balance</span>
            <span className={`account-page__balance-value ${balanceClass}`}>
              {formatMoney(Number(account.balance))}
            </span>
          </div>
        </div>
      </div>

      {showReconcileBanner && accountId && (
        <ReconcileBanner accountId={accountId} accountName={account.name} />
      )}

      {!showReconcileBanner && budgetId && (
        <PendingReviewBanner budgetId={budgetId} accountId={accountId ?? undefined} onView={setTransactionSearch} />
      )}

      {pendingMatches.length > 0 && (
        <div className="account-page__match-banner">
          <span>
            {pendingMatches.length} possible duplicate{pendingMatches.length !== 1 ? 's' : ''} found
            — may match a manually entered transaction
          </span>
          <button
            className="account-page__match-btn account-page__match-btn--review"
            onClick={() => setShowMatchModal(true)}
          >
            Review
          </button>
        </div>
      )}

      {showMatchModal && pendingMatches.length > 0 && (
        <MatchReviewModal matches={pendingMatches} budgetId={budgetId} onClose={() => setShowMatchModal(false)} />
      )}

      <div className="account-page__body">
        <TransactionTable accountId={accountId} budgetId={budgetId} />
      </div>

      {isAccountEditorOpen && editingAccountId && (
        <AccountSettingsModal accountId={editingAccountId} onClose={closeAccountEditor} />
      )}
    </div>
  )
}
