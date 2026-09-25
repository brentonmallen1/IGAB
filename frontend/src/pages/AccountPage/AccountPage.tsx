import { useCallback, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import {
  AlertTriangle,
  CalendarClock,
  Hourglass,
  Link as LinkIcon,
  Lock,
  Pencil,
  Telescope,
  Upload,
  Wallet,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { CsvImportDialog } from '../../components/imports/CsvImportDialog/CsvImportDialog'
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
import {
  formatSyncSummary,
  useSimpleFINConnections,
  useSyncSimpleFIN,
  usePendingMatches,
} from '../../api/simplefin'
import { useAppStore } from '../../stores/appStore'
import { useUIStore } from '../../stores/uiStore'
import { useFormatters } from '../../hooks/useFormatters'
import { resolveHeaderCollapsed } from './headerCollapse'
import { AccountBalances } from './AccountBalances'
import './AccountPage.css'
import { Pill } from '../../components/common/Pill/Pill'
import { Surface } from '../../components/common/Surface'
import { PageHeader } from '../../components/common/PageHeader/PageHeader'
import { useIsMobile } from '../../hooks/useMediaQuery'
import { ageLabel } from '../../utils/age'

function formatReconcileAge(lastReconciledAt: string | null): string {
  if (!lastReconciledAt) return 'Never reconciled'
  return `Reconciled ${ageLabel(lastReconciledAt)}`
}

export function AccountPage() {
  const { formatMoney, formatDate } = useFormatters()
  const isMobile = useIsMobile()
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
  const [showCsvImport, setShowCsvImport] = useState(false)
  const storedHeaderCollapsed = useUIStore((s) => s.accountHeaderCollapsed)
  const setHeaderCollapsed = useUIStore((s) => s.setAccountHeaderCollapsed)

  // The modal asks the opening question; once a statement balance is set the
  // floating bar takes over and tracks the difference live.
  const isReconcilingHere = isReconciling && reconcileAccountId === accountId
  const showReconcileModal = isReconcilingHere && reconcileStatementBalance === null
  const showReconcileBar = isReconcilingHere && reconcileStatementBalance !== null
  // One rule, three inputs — see headerCollapse.ts. Derived rather than
  // stored, so finishing a reconcile restores whatever the person had chosen
  // without anything having to remember it.
  const headerCollapsed = resolveHeaderCollapsed(storedHeaderCollapsed, isMobile, isReconcilingHere)

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
        // The same line the sidebar's sync shows — this page used to compose
        // its own, which went on saying "Imported 0, skipped 586" after the
        // shared one had learned to name a broken link.
        const msg = formatSyncSummary(result)
        setSyncMsg(msg)
        if (result.orphaned_links.length > 0 || result.balance_drift.length > 0) {
          toast.error(msg)
        } else {
          toast.success(msg)
        }
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

  const isConnected = account.simplefin_account_id && account.simplefin_sync_enabled

  return (
    <div className="account-page">
      <Surface variant="chrome" className="account-page__header">
        {/* One row: identity, the balance, the actions. Folded, that is the
            whole header — the balance sits inline and nothing else renders.
            Open, the balance block takes a full line of its own so the
            equation lands predictably rather than by wrap luck. */}
        <div className="account-page__header-left">
          <div className="account-page__identity">
            {/* The name goes to the app header on a phone, with a back chevron
                to Accounts; the pills stay as the page's own first line. */}
            <PageHeader
              title={account.name}
              back
              className="account-page__name-header"
              meta={
                headerCollapsed ? null : (
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
                    {/* The pill states a fact and now offers the question it
                        raises: what is still waiting to be reconciled. A button
                        around it rather than on it — Pill renders a span, and
                        a click handler on a span is not reachable by keyboard. */}
                    <button
                      type="button"
                      className="account-page__pill-button"
                      onClick={() => setTransactionSearch('is: unreconciled')}
                      title="Show everything this account still has to reconcile"
                    >
                      <Pill tone="outline">
                        <Lock size={12} />
                        {formatReconcileAge(account.last_reconciled_at)}
                      </Pill>
                    </button>
                    {/* Rows before this date are deliberately not flagged as
                        needing a category, so the date has to be visible
                        somewhere. An unexplained absence of nagging is as
                        confusing as the nagging it replaced. */}
                    {account.budget_start_date && (
                      <Pill
                        tone="outline"
                        title={
                          'Anything before this date is opening balance: kept in the register, left ' +
                          'uncategorized on purpose, and not counted as needing a category. On a card ' +
                          'it shows as debt not covered and is paid down by assigning to the card.'
                        }
                      >
                        <CalendarClock size={12} />
                        Budget starts {formatDate(account.budget_start_date)}
                      </Pill>
                    )}
                  </div>
                )
              }
            />
          </div>
          {/* The working balance is stated ONCE, and which spelling you get
              is the fold: folded it is the headline beside the name, open it
              is the `=` term of the equation. Rendering both is what made the
              old header repeat the same number twice, at the same size, three
              lines apart. AccountBalances.test.tsx holds it to once. */}
          <AccountBalances
            balance={account.balance}
            clearedBalance={account.cleared_balance}
            unclearedBalance={account.uncleared_balance}
            collapsed={headerCollapsed}
            onToggle={() => setHeaderCollapsed(!headerCollapsed)}
            formatMoney={formatMoney}
          />
          {/* Outside the equation on purpose. Pending rows are visible in the
              register and counted in none of the three figures above — an
              auth hold is provisional and the money moves once, at posting
              (backend: txn_filters.PENDING_ROW). That is defensible and it is
              also why the total has to be said: otherwise the register shows
              rows that add up to nothing anywhere. */}
          {!headerCollapsed && account.pending_balance !== 0 && (
            <div className="account-page__pending">
              <Hourglass size={11} aria-hidden />
              <span className="account-page__pending-value tabular">
                {formatMoney(account.pending_balance)}
              </span>
              <span>pending — not in the balances above until it posts</span>
            </div>
          )}
          {/* The bank's own figure, written every sync. Shown only when it
              disagrees with the cleared balance — agreement is the normal
              state and needs no line. `bank_drift` is served: the sync
              decides on the same rule whether a run is degraded. On an
              account that gets reconciled, a gap after a sync usually means
              rows the sync never asked for, so the line says so and names
              both ways back to agreement. */}
          {!headerCollapsed &&
            account.bank_drift !== null &&
            account.simplefin_balance !== null &&
            account.bank_drift !== 0 && (
              <div
                className={`account-page__bank-reports${
                  account.last_reconciled_at ? ' account-page__bank-reports--fault' : ''
                }`}
              >
                <AlertTriangle size={11} aria-hidden />
                <span>
                  Bank reports {formatMoney(account.simplefin_balance)} —{' '}
                  {formatMoney(Math.abs(account.bank_drift))}{' '}
                  {account.bank_drift > 0 ? 'more' : 'less'} than the cleared balance here.
                  {account.last_reconciled_at
                    ? ' Something may not have been pulled in: fetch the last 90 days again from account settings, then reconcile.'
                    : ' Reconcile to bring them together.'}
                </span>
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
          {/* The file a bank exports IS this account's transactions, so the
              import belongs here rather than on a page that has to ask which
              account you meant. */}
          <button
            className="account-page__action-btn"
            onClick={() => setShowCsvImport(true)}
            aria-label="Import transactions from CSV"
            title="Import transactions from CSV"
          >
            <Upload size={16} />
          </button>
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

      {showCsvImport && accountId && budgetId && (
        <CsvImportDialog
          budgetId={budgetId}
          accountId={accountId}
          accountName={account.name}
          onClose={() => setShowCsvImport(false)}
        />
      )}

      {showReconcileBar && accountId && <ReconcileStatusBar accountId={accountId} />}

      {/* Everything the page wants to say before the register, as one stack
          with one rhythm — terms, a review count, possible duplicates. */}
      <div className="account-page__notices">
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
              {pendingMatches.length} possible duplicate{pendingMatches.length !== 1 ? 's' : ''}{' '}
              found — may match a manually entered transaction
            </span>
            <button
              className="account-page__match-btn account-page__match-btn--review"
              onClick={() => setShowMatchModal(true)}
            >
              Review
            </button>
          </div>
        )}
      </div>

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
