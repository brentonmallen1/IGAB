import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { TransactionTable } from '../../components/transactions/TransactionTable/TransactionTable'
import { ReconcileBanner } from '../../components/accounts/ReconcileBanner'
import { useAccounts } from '../../api/accounts'
import { useSimpleFINConnections, useSyncSimpleFIN } from '../../api/simplefin'
import { useAppStore } from '../../stores/appStore'
import { useUIStore } from '../../stores/uiStore'
import { formatMoney } from '../../utils/money'
import './AccountPage.css'

export function AccountPage() {
  const { accountId } = useParams<{ accountId: string }>()
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const setSelectedAccount = useAppStore((s) => s.setSelectedAccountId)
  const { data: accounts } = useAccounts(budgetId)

  const account = accounts?.find((a) => a.id === accountId)
  const { isReconciling, reconcileAccountId, startReconciliation } = useUIStore()
  const { data: sfConnections } = useSimpleFINConnections()
  const firstConnection = sfConnections?.[0]
  const sync = useSyncSimpleFIN(budgetId)
  const [syncMsg, setSyncMsg] = useState<string | null>(null)

  const showReconcileBanner = isReconciling && reconcileAccountId === accountId

  useEffect(() => {
    if (accountId) setSelectedAccount(accountId)
    return () => setSelectedAccount(null)
  }, [accountId, setSelectedAccount])

  async function handleSync() {
    if (!firstConnection) return
    setSyncMsg(null)
    try {
      const result = await sync.mutateAsync(firstConnection.id)
      setSyncMsg(`Imported ${result.imported}, skipped ${result.skipped}`)
    } catch {
      setSyncMsg('Sync failed')
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
          {account.simplefin_account_id && firstConnection && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <button
                className="account-page__sync-btn"
                onClick={handleSync}
                disabled={sync.isPending}
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

      <div className="account-page__body">
        <TransactionTable accountId={accountId} budgetId={budgetId} />
      </div>
    </div>
  )
}
