import type { ReactNode } from 'react'
import { Lock, Pencil, RefreshCw, ScanSearch, Upload, type LucideIcon } from 'lucide-react'
import type { Account } from '../../types'
import { BottomSheet } from '../../components/common/BottomSheet/BottomSheet'
import { BalanceEquation } from './AccountBalances'
import { AccountStatusPills, BankDriftLine, PendingLine } from './AccountFacts'
import type { DriftNotice } from './bankDriftNotice'
import './AccountSheets.css'

interface Props {
  open: boolean
  onClose: () => void
  account: Pick<
    Account,
    | 'name'
    | 'balance'
    | 'cleared_balance'
    | 'uncleared_balance'
    | 'pending_balance'
    | 'on_budget'
    | 'last_reconciled_at'
    | 'budget_start_date'
  >
  isConnected: boolean
  formatMoney: (amount: number) => string
  formatDate: (date: string) => string
  drift: DriftNotice | null
  /** A debt account's terms (LiabilityTermsHeader), or null. */
  terms: ReactNode
  onShowUnreconciled: () => void
  /** Null when the account is not connected to a bank. */
  onSync: (() => void) | null
  syncing: boolean
  onImport: () => void
  onScanDuplicates: () => void
  scanning: boolean
  onEdit: () => void
  /** Null where Reconcile is already the header row's button. */
  onReconcile: (() => void) | null
}

interface Action {
  id: string
  label: string
  icon: LucideIcon
  run: () => void
  disabled?: boolean
}

/**
 * Everything the desktop header shows that the phone's one row does not:
 * the balance equation, pending money, the bank's figure, the account's
 * standing facts, a debt's terms, and the actions.
 *
 * The parts are the desktop's own components (BalanceEquation,
 * AccountFacts), so the sheet cannot word or colour a figure the header
 * words differently. An action closes the sheet before it runs — each one
 * opens a dialog or a toast of its own, which must not stack under a sheet.
 */
export function AccountToolsSheet({
  open,
  onClose,
  account,
  isConnected,
  formatMoney,
  formatDate,
  drift,
  terms,
  onShowUnreconciled,
  onSync,
  syncing,
  onImport,
  onScanDuplicates,
  scanning,
  onEdit,
  onReconcile,
}: Props) {
  const actions: Action[] = [
    ...(onReconcile ? [{ id: 'reconcile', label: 'Reconcile', icon: Lock, run: onReconcile }] : []),
    ...(onSync
      ? [
          {
            id: 'sync',
            label: syncing ? 'Syncing…' : 'Sync now',
            icon: RefreshCw,
            run: onSync,
            disabled: syncing,
          },
        ]
      : []),
    { id: 'import', label: 'Import a CSV', icon: Upload, run: onImport },
    {
      id: 'duplicates',
      label: 'Find possible duplicates',
      icon: ScanSearch,
      run: onScanDuplicates,
      disabled: scanning,
    },
    { id: 'edit', label: 'Edit account', icon: Pencil, run: onEdit },
  ]

  return (
    <BottomSheet
      open={open}
      onClose={onClose}
      height="auto"
      title={account.name}
      historyKey="account-tools"
    >
      <div className="account-sheet">
        <section className="account-sheet__section" aria-label="Balances">
          <h3 className="account-sheet__heading">Balances</h3>
          <BalanceEquation
            balance={account.balance}
            clearedBalance={account.cleared_balance}
            unclearedBalance={account.uncleared_balance}
            formatMoney={formatMoney}
          />
          <PendingLine
            amount={account.pending_balance}
            formatted={formatMoney(account.pending_balance)}
          />
          <BankDriftLine notice={drift} />
        </section>

        <section className="account-sheet__section" aria-label="This account">
          <h3 className="account-sheet__heading">This account</h3>
          <AccountStatusPills
            account={account}
            isConnected={isConnected}
            formatDate={formatDate}
            onShowUnreconciled={() => {
              onClose()
              onShowUnreconciled()
            }}
          />
        </section>

        {terms && (
          <section className="account-sheet__section" aria-label="Terms">
            <h3 className="account-sheet__heading">Terms</h3>
            {terms}
          </section>
        )}

        <section className="account-sheet__section" aria-label="Actions">
          <h3 className="account-sheet__heading">Actions</h3>
          {actions.map(({ id, label, icon: Icon, run, disabled }) => (
            <button
              key={id}
              type="button"
              className="account-sheet__action"
              disabled={disabled}
              onClick={() => {
                onClose()
                run()
              }}
            >
              <Icon size={18} aria-hidden="true" />
              <span>{label}</span>
            </button>
          ))}
        </section>
      </div>
    </BottomSheet>
  )
}
