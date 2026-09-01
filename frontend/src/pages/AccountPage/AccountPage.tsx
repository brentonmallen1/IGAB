import { useCallback, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import {
  CalendarClock,
  CheckCircle,
  CircleDot,
  Link as LinkIcon,
  Lock,
  Pencil,
  Telescope,
  Wallet,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { TransactionTable } from '../../components/transactions/TransactionTable/TransactionTable'
import { ReconcileModal } from '../../components/accounts/ReconcileModal'
import { ReconcileStatusBar } from '../../components/accounts/ReconcileStatusBar'
import { PendingReviewBanner } from '../../components/accounts/PendingReviewBanner'
import { AccountSettingsModal } from '../../components/accounts/AccountSettingsModal'
import { CardPaymentModal } from '../../components/accounts/CardPaymentModal'
import { LiabilityTermsHeader } from '../../components/liabilities/LiabilityTermsHeader'
import { LiabilitySettingsModal } from '../../components/liabilities/LiabilitySettingsModal'
import { MatchReviewModal } from '../../components/simplefin/MatchReviewModal'
import { useAccounts } from '../../api/accounts'
import { useLiabilities } from '../../api/liabilities'
import { useSimpleFINConnections, useSyncSimpleFIN, usePendingMatches } from '../../api/simplefin'
import { useAppStore } from '../../stores/appStore'
import { useUIStore } from '../../stores/uiStore'
import { useFormatters } from '../../hooks/useFormatters'
import './AccountPage.css'
import { Pill } from '../../components/common/Pill/Pill'
import { Surface } from '../../components/common/Surface'

function formatReconcileAge(lastReconciledAt: string | null): string {
  if (!lastReconciledAt) return 'Never reconciled'
  const ageMs = Date.now() - new Date(lastReconciledAt).getTime()
  const ageDays = Math.floor(ageMs / (1000 * 60 * 60 * 24))
  if (ageDays === 0) return 'Reconciled today'
  if (ageDays === 1) return 'Reconciled yesterday'
  return `Reconciled ${ageDays} days ago`
}

export function AccountPage() {
  const { formatMoney, formatDate } = useFormatters()
  const { accountId } = useParams<{ accountId: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const highlightId = searchParams.get('highlight')
  const budgetId = useAppStore((s) => s.currentBudgetId)

  const clearHighlight = useCallback(() => {
    if (highlightId) {
      setSearchParams(
        (prev) => {
          prev.delete('highlight')
          return prev
        },
        { replace: true }
      )
    }
  }, [highlightId, setSearchParams])
  const { data: accounts } = useAccounts(budgetId)

  const account = accounts?.find((a) => a.id === accountId)
  const {
    isReconciling,
    reconcileAccountId,
    reconcileStatementBalance,
    startReconciliation,
    setTransactionSearch,
  } = useUIStore()
  const { data: sfConnections } = useSimpleFINConnections()
  const firstConnection = sfConnections?.[0] ?? null
  const sync = useSyncSimpleFIN(budgetId)
  const [syncMsg, setSyncMsg] = useState<string | null>(null)
  const activeModal = useUIStore((s) => s.activeModal)
  const openModal = useUIStore((s) => s.openModal)
  const closeModal = useUIStore((s) => s.closeModal)
  const { data: liabilities = [] } = useLiabilities(budgetId)
  const { data: pendingMatches = [] } = usePendingMatches(budgetId)
  const [showMatchModal, setShowMatchModal] = useState(false)

  // The modal asks the opening question; once a statement balance is set the
  // floating bar takes over and tracks the difference live.
  const isReconcilingHere = isReconciling && reconcileAccountId === accountId
  const showReconcileModal = isReconcilingHere && reconcileStatementBalance === null
  const showReconcileBar = isReconcilingHere && reconcileStatementBalance !== null

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

  const clearedClass = account.cleared_balance < 0 ? 'negative' : 'positive'
  const workingClass = account.balance < 0 ? 'negative' : 'positive'
  const isConnected = account.simplefin_account_id && account.simplefin_sync_enabled

  return (
    <div className="account-page">
      <Surface variant="chrome" className="account-page__header">
        {/* Left: Account identity + balances stacked */}
        <div className="account-page__header-left">
          <div className="account-page__identity">
            <h1 className="account-page__name">{account.name}</h1>
            <div className="account-page__status-row">
              {account.on_budget ? (
                <Pill
                  tone="outline"
                  title="On budget — spending here comes out of your envelope categories"
                >
                  <Wallet size={12} />
                  On budget
                </Pill>
              ) : (
                <Pill
                  tone="outline"
                  title="Tracking — counted in net worth only; transactions here don't need categories"
                >
                  <Telescope size={12} />
                  Tracking
                </Pill>
              )}
              {isConnected && (
                <Pill tone="positive">
                  <LinkIcon size={12} />
                  Connected
                </Pill>
              )}
              <Pill tone="outline">
                <Lock size={12} />
                {formatReconcileAge(account.last_reconciled_at)}
              </Pill>
              {/* Rows before this date are deliberately not flagged as needing
                  a category, so the date has to be visible somewhere. An
                  unexplained absence of nagging is as confusing as the nagging
                  it replaced. */}
              {account.budget_start_date && (
                <Pill
                  tone="outline"
                  title={
                    'Anything before this date is opening balance: kept in the register, left ' +
                    'uncategorized on purpose, and not counted as needing a category. On a card ' +
                    'it shows as Uncovered and is paid down by assigning to the card.'
                  }
                >
                  <CalendarClock size={12} />
                  Budget starts {formatDate(account.budget_start_date)}
                </Pill>
              )}
            </div>
          </div>
          <div className="account-page__balances">
            <div className="account-page__balance-item">
              <span className={`account-page__balance-value ${clearedClass}`}>
                {formatMoney(account.cleared_balance)}
              </span>
              <span className="account-page__balance-label">
                <CheckCircle size={10} />
                Cleared Balance
              </span>
            </div>
            <span className="account-page__balance-op">+</span>
            <div className="account-page__balance-item">
              <span className="account-page__balance-value">
                {formatMoney(account.uncleared_balance)}
              </span>
              <span className="account-page__balance-label">
                <CircleDot size={10} />
                Uncleared Balance
              </span>
            </div>
            <span className="account-page__balance-op">=</span>
            <div className="account-page__balance-item account-page__balance-item--working">
              <span className={`account-page__balance-value ${workingClass}`}>
                {formatMoney(account.balance)}
              </span>
              <span className="account-page__balance-label">Working Balance</span>
            </div>
          </div>
          {/* The bank's own figure, written every sync. Shown only when it
              disagrees with the cleared balance — agreement is the normal
              state and needs no line — and it names the fix rather than
              adjusting anything itself: drift is Reconcile's job. */}
          {account.simplefin_balance !== null &&
            account.simplefin_balance !== account.cleared_balance && (
              <div className="account-page__bank-reports">
                Bank reports {formatMoney(account.simplefin_balance)} — differs from the cleared
                balance by{' '}
                {formatMoney(Math.abs(account.simplefin_balance - account.cleared_balance))}.
                Reconcile to bring them together.
              </div>
            )}
        </div>

        {/* Right: Actions (vertically centered) */}
        <div className="account-page__actions">
          <button
            className="account-page__action-btn"
            onClick={() => openModal('account', accountId!)}
            aria-label="Edit account"
            title="Edit account"
          >
            <Pencil size={16} />
          </button>
          {isConnected && (
            <button
              className="account-page__action-btn account-page__action-btn--sync"
              onClick={handleSync}
              disabled={sync.isPending || !firstConnection}
            >
              {sync.isPending ? 'Syncing…' : 'Sync'}
            </button>
          )}
          <button
            className="account-page__reconcile-btn"
            onClick={() => startReconciliation(accountId!)}
            disabled={isReconcilingHere}
          >
            Reconcile
          </button>
          {syncMsg && <span className="account-page__sync-msg">{syncMsg}</span>}
        </div>
      </Surface>

      {showReconcileModal && accountId && (
        <ReconcileModal accountId={accountId} accountName={account.name} />
      )}

      {showReconcileBar && accountId && <ReconcileStatusBar accountId={accountId} />}

      {/* A debt account has APR and a minimum payment whether or not anyone has
          entered them, so the page has a place for them either way. Cards get
          the same header loans do — one pattern, no "add your APR" banner. */}
      {account.classification === 'liability' && budgetId && accountId && (
        <LiabilityTermsHeader
          budgetId={budgetId}
          accountId={accountId}
          isLoan={!account.on_budget}
        />
      )}

      {!isReconcilingHere && budgetId && (
        <PendingReviewBanner
          budgetId={budgetId}
          accountId={accountId ?? undefined}
          onView={setTransactionSearch}
        />
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
        <MatchReviewModal
          matches={pendingMatches}
          budgetId={budgetId}
          onClose={() => setShowMatchModal(false)}
        />
      )}

      <div className="account-page__body">
        <TransactionTable
          accountId={accountId}
          budgetId={budgetId}
          highlightId={highlightId}
          onInteraction={clearHighlight}
        />
      </div>

      {activeModal?.kind === 'account' && activeModal.editingId && (
        <AccountSettingsModal accountId={activeModal.editingId} onClose={closeModal} />
      )}

      {activeModal?.kind === 'card-payment' && activeModal.editingId && budgetId && (
        <CardPaymentModal
          budgetId={budgetId}
          accountId={activeModal.editingId}
          onClose={closeModal}
        />
      )}

      {activeModal?.kind === 'liability' && activeModal.editingId && budgetId && (
        <LiabilitySettingsModal
          budgetId={budgetId}
          liability={liabilities.find((l) => l.id === activeModal.editingId) ?? null}
          onClose={closeModal}
        />
      )}
    </div>
  )
}
