import { useCallback, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { Pencil, ScanSearch, Upload } from 'lucide-react'
import toast from 'react-hot-toast'
import { CsvImportDialog } from '../../components/imports/CsvImportDialog/CsvImportDialog'
import { TransactionTable } from '../../components/transactions/TransactionTable/TransactionTable'
import { registerPayAction } from '../../components/transactions/TransactionTable/payButton'
import { ReconcileModal } from '../../components/accounts/ReconcileModal'
import { ReconcileStatusBar } from '../../components/accounts/ReconcileStatusBar'
import { PendingReviewBanner } from '../../components/accounts/PendingReviewBanner'
import { REVIEW_SEARCH } from '../../components/accounts/pendingReview'
import { AccountSettingsModal } from '../../components/accounts/AccountSettingsModal'
import { CardPaymentModal } from '../../components/accounts/CardPaymentModal'
import { LiabilityTermsHeader } from '../../components/liabilities/LiabilityTermsHeader'
import { LiabilitySettingsModal } from '../../components/liabilities/LiabilitySettingsModal'
import { MatchReviewModal } from '../../components/simplefin/MatchReviewModal'
import { useAccounts, useScanDuplicates } from '../../api/accounts'
import { useLiabilities } from '../../api/liabilities'
import { usePendingReviewCountForAccount } from '../../api/transactions'
import {
  formatSyncSummary,
  useSimpleFINConnections,
  useSyncSimpleFIN,
  usePendingMatchesForAccount,
} from '../../api/simplefin'
import { useAppStore } from '../../stores/appStore'
import { useUIStore } from '../../stores/uiStore'
import { useFormatters } from '../../hooks/useFormatters'
import { resolveHeaderCollapsed } from './headerCollapse'
import { AccountBalances } from './AccountBalances'
import { AccountStatusPills, BankDriftLine, PendingLine } from './AccountFacts'
import { AccountPhoneHeader } from './AccountPhoneHeader'
import { AccountToolsSheet } from './AccountToolsSheet'
import { AccountNoticesSheet } from './AccountNoticesSheet'
import { accountNotices, duplicatesPhrase } from './accountNotices'
import { bankDriftNotice } from './bankDriftNotice'
import './AccountPage.css'
import { Surface } from '../../components/common/Surface'
import { PageHeader } from '../../components/common/PageHeader/PageHeader'
import { useIsMobile } from '../../hooks/useMediaQuery'

export function AccountPage() {
  const { formatMoney, formatDate, formatDateTime } = useFormatters()
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
    cancelReconciliation,
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
  // This account's, not the budget's: the banner sits on one register.
  const { data: pendingMatches = [] } = usePendingMatchesForAccount(accountId ?? null)
  // The banner's own query (react-query shares it): the phone's notice pill
  // counts what the desktop banner counts.
  const { data: reviewCounts } = usePendingReviewCountForAccount(accountId ?? null)
  const [showMatchModal, setShowMatchModal] = useState(false)
  const [toolsOpen, setToolsOpen] = useState(false)
  const [noticesOpen, setNoticesOpen] = useState(false)
  const scanDuplicates = useScanDuplicates()
  // The scan lived at the bottom of the Edit account dialog, where nobody
  // found it; the page said nothing about duplicates until some were pending.
  const handleScanDuplicates = async () => {
    if (!accountId) return
    try {
      const { created } = await scanDuplicates.mutateAsync(accountId)
      if (created === 0) {
        toast.success('No new possible duplicates in this account')
      } else {
        setShowMatchModal(true)
      }
    } catch {
      toast.error('The duplicate scan failed')
    }
  }
  const [showCsvImport, setShowCsvImport] = useState(false)
  const storedHeaderCollapsed = useUIStore((s) => s.accountHeaderCollapsed)
  const setHeaderCollapsed = useUIStore((s) => s.setAccountHeaderCollapsed)

  // The modal asks the opening question; once a statement balance is set the
  // floating bar takes over and tracks the difference live.
  const isReconcilingHere = isReconciling && reconcileAccountId === accountId
  const showReconcileModal = isReconcilingHere && reconcileStatementBalance === null
  const showReconcileBar = isReconcilingHere && reconcileStatementBalance !== null
  // One rule, two inputs — see headerCollapse.ts. Derived rather than
  // stored, so finishing a reconcile restores whatever the person had chosen
  // without anything having to remember it. Desktop only: a phone has no fold.
  const headerCollapsed = resolveHeaderCollapsed(storedHeaderCollapsed, isReconcilingHere)

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

  const isConnected = Boolean(account.simplefin_account_id && account.simplefin_sync_enabled)
  const payAction = registerPayAction(accounts ?? [], accountId)
  const showUnreconciled = () => setTransactionSearch('is: unreconciled')

  // The bank's own figure, written every sync. Said only when it disagrees
  // with the cleared balance — agreement is the normal state and needs no
  // line. Every figure here is served, including WHY the two differ and
  // whether the sync calls it a fault: the sync decides both on the same
  // rule, and a page that decided for itself would be free to disagree with
  // the sync badge.
  //
  // The wording is the fix. One sentence used to serve all three causes, and
  // it named the one that means missing rows — so a ledger running AHEAD of a
  // lagging feed (ticking a hold cleared that the bank's site already shows
  // posted) told the user to refetch 90 days and find nothing. See
  // ./bankDriftNotice.ts.
  const driftNotice =
    account.simplefin_balance !== null && account.bank_drift !== null
      ? bankDriftNotice(
          {
            reported: account.simplefin_balance,
            drift: account.bank_drift,
            unexplained: account.bank_drift_unexplained ?? account.bank_drift,
            unposted: account.bank_unposted_cleared ?? 0,
            inReview: account.bank_in_review ?? 0,
            reason: account.bank_drift_reason ?? 'unexplained',
            isFault: account.bank_drift_is_fault,
            asOf: account.simplefin_balance_date
              ? formatDateTime(account.simplefin_balance_date)
              : null,
            reconciled: account.last_reconciled_at !== null,
          },
          formatMoney
        )
      : null

  // What the phone's notice pill stands for. While reconciling the review
  // banner steps aside; so does its notice.
  const notices = accountNotices({
    review: isReconcilingHere ? null : reviewCounts,
    duplicates: pendingMatches.length,
    drift: driftNotice,
  })

  // A debt account has APR and a minimum payment whether or not anyone has
  // entered them, so the page has a place for them either way. Cards get the
  // same header loans do — one pattern, no "add your APR" banner. On a phone
  // it moves into Tools: it never folded, and it was the card page's tallest
  // band.
  const terms =
    account.classification === 'liability' ? (
      <LiabilityTermsHeader budgetId={budgetId} accountId={accountId} isLoan={!account.on_budget} />
    ) : null

  return (
    <div className="account-page">
      {isMobile ? (
        <>
          {/* The name and the back chevron, portalled into the app bar. No
              meta: on a phone the pills live in Tools, so PageHeader draws no
              band of its own here. */}
          <PageHeader title={account.name} back />
          <AccountPhoneHeader
            balance={account.balance}
            formatMoney={formatMoney}
            notices={notices}
            // A debt account's main action is its payment; Reconcile moves
            // into Tools there. Everywhere else Reconcile is the button.
            primary={
              payAction
                ? {
                    label: payAction.shortLabel,
                    onClick: () => openModal('card-payment', accountId),
                  }
                : {
                    label: 'Reconcile',
                    onClick: () => startReconciliation(accountId),
                    disabled: isReconcilingHere,
                  }
            }
            onOpenTools={() => setToolsOpen(true)}
            onOpenNotices={() => setNoticesOpen(true)}
          />
          <AccountToolsSheet
            open={toolsOpen}
            onClose={() => setToolsOpen(false)}
            account={account}
            isConnected={isConnected}
            formatMoney={formatMoney}
            formatDate={formatDate}
            drift={driftNotice}
            terms={terms}
            onShowUnreconciled={showUnreconciled}
            onSync={isConnected && firstConnection ? () => void handleSync() : null}
            syncing={sync.isPending}
            onImport={() => setShowCsvImport(true)}
            onScanDuplicates={() => void handleScanDuplicates()}
            scanning={scanDuplicates.isPending}
            onEdit={() => openModal('account', accountId)}
            onReconcile={
              payAction && !isReconcilingHere ? () => startReconciliation(accountId) : null
            }
          />
          <AccountNoticesSheet
            open={noticesOpen}
            onClose={() => setNoticesOpen(false)}
            notices={notices}
            onReviewDuplicates={() => setShowMatchModal(true)}
            onViewReview={() => setTransactionSearch(REVIEW_SEARCH)}
          />
        </>
      ) : (
        <Surface variant="chrome" className="account-page__header">
          {/* One row: identity, the balance, the actions. Folded, that is the
              whole header — the balance sits inline and nothing else renders.
              Open, the balance block takes a full line of its own so the
              equation lands predictably rather than by wrap luck. */}
          <div className="account-page__header-left">
            <div className="account-page__identity">
              <PageHeader
                title={account.name}
                back
                className="account-page__name-header"
                meta={
                  headerCollapsed ? null : (
                    <AccountStatusPills
                      account={account}
                      isConnected={isConnected}
                      formatDate={formatDate}
                      onShowUnreconciled={showUnreconciled}
                    />
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
            {!headerCollapsed && (
              <>
                <PendingLine
                  amount={account.pending_balance}
                  formatted={formatMoney(account.pending_balance)}
                />
                <BankDriftLine notice={driftNotice} />
              </>
            )}
          </div>

          {/* Right: Actions (vertically centered) */}
          <div className="account-page__actions">
            <button
              className="account-page__action-btn"
              onClick={() => openModal('account', accountId)}
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
              className="account-page__action-btn"
              onClick={() => void handleScanDuplicates()}
              disabled={scanDuplicates.isPending}
              aria-label="Find possible duplicates"
              title="Find possible duplicates"
            >
              <ScanSearch size={16} />
            </button>
            <button
              className="account-page__reconcile-btn"
              onClick={() => startReconciliation(accountId)}
              disabled={isReconcilingHere}
            >
              Reconcile
            </button>
            {syncMsg && <span className="account-page__sync-msg">{syncMsg}</span>}
          </div>
        </Surface>
      )}

      {showReconcileModal && (
        <ReconcileModal
          accountId={accountId}
          accountName={account.name}
          onReviewDuplicates={() => {
            // Settle first, then reconcile: the question the modal asks is
            // about a balance the open pairs make too large.
            cancelReconciliation()
            setShowMatchModal(true)
          }}
        />
      )}

      {showCsvImport && (
        <CsvImportDialog
          budgetId={budgetId}
          accountId={accountId}
          accountName={account.name}
          onClose={() => setShowCsvImport(false)}
        />
      )}

      {showReconcileBar && (
        <ReconcileStatusBar
          accountId={accountId}
          onReviewDuplicates={() => setShowMatchModal(true)}
        />
      )}

      {/* Everything the page wants to say before the register, as one stack
          with one rhythm — terms, a review count, possible duplicates. On a
          phone all three live behind the header row instead (the notice pill
          and Tools), so nothing stacks above the register there. */}
      {!isMobile && (
        <div className="account-page__notices">
          {terms}

          {!isReconcilingHere && (
            <PendingReviewBanner
              budgetId={budgetId}
              accountId={accountId}
              onView={setTransactionSearch}
            />
          )}

          {pendingMatches.length > 0 && (
            <div className="account-page__match-banner">
              <span>
                {duplicatesPhrase(pendingMatches.length)} found — may match a manually entered
                transaction
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

      {activeModal?.kind === 'card-payment' && activeModal.editingId && (
        <CardPaymentModal
          budgetId={budgetId}
          accountId={activeModal.editingId}
          onClose={closeModal}
        />
      )}

      {activeModal?.kind === 'liability' && activeModal.editingId && (
        <LiabilitySettingsModal
          budgetId={budgetId}
          liability={liabilities.find((l) => l.id === activeModal.editingId) ?? null}
          onClose={closeModal}
        />
      )}
    </div>
  )
}
