import {
  AlertTriangle,
  CalendarClock,
  Hourglass,
  Link as LinkIcon,
  Lock,
  Telescope,
  Wallet,
} from 'lucide-react'
import type { Account } from '../../types'
import { BUDGET_START_NOTE } from '../../components/accounts/budgetStartNote'
import { Pill } from '../../components/common/Pill/Pill'
import { ageLabel } from '../../utils/age'
import type { DriftNotice } from './bankDriftNotice'

/**
 * The account's standing facts — what it is, whether it is connected, when it
 * was last reconciled, where its budget starts — and the two lines that
 * explain the balances: pending money, and the bank's own figure.
 *
 * The desktop header draws them under its fold; the phone draws them in the
 * Tools sheet. One component each, so the two places cannot word a fact
 * differently.
 */

function formatReconcileAge(lastReconciledAt: string | null): string {
  if (!lastReconciledAt) return 'Never reconciled'
  return `Reconciled ${ageLabel(lastReconciledAt)}`
}

export function AccountStatusPills({
  account,
  isConnected,
  formatDate,
  onShowUnreconciled,
}: {
  account: Pick<Account, 'on_budget' | 'last_reconciled_at' | 'budget_start_date'>
  isConnected: boolean
  formatDate: (date: string) => string
  onShowUnreconciled: () => void
}) {
  return (
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
      {/* The pill states a fact and now offers the question it raises: what
          is still waiting to be reconciled. A button around it rather than on
          it — Pill renders a span, and a click handler on a span is not
          reachable by keyboard. */}
      <button
        type="button"
        className="account-page__pill-button"
        onClick={onShowUnreconciled}
        title="Show everything this account still has to reconcile"
      >
        <Pill tone="outline">
          <Lock size={12} />
          {formatReconcileAge(account.last_reconciled_at)}
        </Pill>
      </button>
      {/* Rows before this date are deliberately not flagged as needing a
          category, nor counted in reports, so the date has to be visible
          somewhere. An unexplained absence of nagging is as confusing as the
          nagging it replaced. */}
      {account.budget_start_date && (
        <Pill tone="outline" title={BUDGET_START_NOTE}>
          <CalendarClock size={12} />
          Budget starts {formatDate(account.budget_start_date)}
        </Pill>
      )}
    </div>
  )
}

/**
 * Outside the equation on purpose. Pending rows are visible in the register
 * and counted in none of the three figures — an auth hold is provisional and
 * the money moves once, at posting (backend: txn_filters.PENDING_ROW). That
 * is defensible and it is also why the total has to be said: otherwise the
 * register shows rows that add up to nothing anywhere.
 */
export function PendingLine({ amount, formatted }: { amount: number; formatted: string }) {
  if (amount === 0) return null
  return (
    <div className="account-page__pending">
      <Hourglass size={11} aria-hidden />
      <span className="account-page__pending-value tabular">{formatted}</span>
      <span>pending — not in the balances above until it posts</span>
    </div>
  )
}

/** The bank's sentence (./bankDriftNotice.ts), in the sync's own tone. */
export function BankDriftLine({ notice }: { notice: DriftNotice | null }) {
  if (notice === null) return null
  return (
    <div
      className={`account-page__bank-reports${
        notice.tone === 'fault' ? ' account-page__bank-reports--fault' : ''
      }`}
    >
      <AlertTriangle size={11} aria-hidden />
      <span>{notice.text}</span>
    </div>
  )
}
