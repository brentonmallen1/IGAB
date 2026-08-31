import { useState } from 'react'
import { useAppStore } from '../../stores/appStore'
import {
  useScheduledTransactions,
  useSkipScheduledTransaction,
  useEnterScheduledTransaction,
} from '../../api/scheduledTransactions'
import { useAccounts } from '../../api/accounts'
import { usePayees } from '../../api/transactions'
import { ScheduledTransactionEditor } from '../../components/scheduled/ScheduledTransactionEditor'
import { useFormatters } from '../../hooks/useFormatters'
import type { ScheduledTransaction } from '../../types'
import './ScheduledTransactionsPage.css'

const FREQ_LABELS: Record<string, string> = {
  daily: 'Daily',
  weekly: 'Weekly',
  biweekly: 'Every 2 weeks',
  monthly: 'Monthly',
  yearly: 'Yearly',
}

export function ScheduledTransactionsPage() {
  const { formatMoney } = useFormatters()
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data: scheduled = [] } = useScheduledTransactions(budgetId)
  const { data: accounts = [] } = useAccounts(budgetId)
  const { data: payees = [] } = usePayees(budgetId)
  const skip = useSkipScheduledTransaction(budgetId ?? '')
  const enter = useEnterScheduledTransaction(budgetId ?? '')
  const [editing, setEditing] = useState<ScheduledTransaction | null | 'new'>(null)

  if (!budgetId) {
    return (
      <div className="sched-page">
        <div className="sched-empty">Select a budget to view scheduled transactions.</div>
      </div>
    )
  }

  function accountName(id: string) {
    return accounts.find((a) => a.id === id)?.name ?? id
  }

  function payeeName(s: ScheduledTransaction) {
    if (s.transfer_account_id) return `Transfer: ${accountName(s.transfer_account_id)}`
    if (s.payee_id) return payees.find((p) => p.id === s.payee_id)?.name ?? '—'
    return '—'
  }

  return (
    <div className="sched-page page-fill">
      <div className="sched-header">
        <h1 className="sched-title">Scheduled Transactions</h1>
        <button className="sched-btn sched-btn--primary" onClick={() => setEditing('new')}>
          + New
        </button>
      </div>

      {editing && (
        <ScheduledTransactionEditor
          budgetId={budgetId}
          existing={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}

      {scheduled.length === 0 ? (
        <div className="sched-empty">
          No scheduled transactions. Create one to auto-post recurring bills.
        </div>
      ) : (
        <div className="sched-table surface scroll-fill">
          <div className="sched-table__head">
            <span>Account</span>
            <span>Payee</span>
            <span>Amount</span>
            <span>Frequency</span>
            <span>Next Date</span>
            <span>Auto</span>
            <span></span>
          </div>
          {scheduled.map((s) => (
            <div
              key={s.id}
              className="sched-table__row"
              role="button"
              tabIndex={0}
              onClick={() => setEditing(s)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  setEditing(s)
                }
              }}
            >
              <span className="sched-cell--account">{accountName(s.account_id)}</span>
              <span className="sched-cell--payee">{payeeName(s)}</span>
              <span className={`sched-cell--amount ${s.amount < 0 ? 'negative' : 'positive'}`}>
                {formatMoney(Math.abs(s.amount))}
                {s.amount < 0 ? ' out' : ' in'}
              </span>
              <span className="sched-cell--freq">{FREQ_LABELS[s.frequency] ?? s.frequency}</span>
              <span className="sched-cell--date">{s.next_occurrence_date}</span>
              <span className="sched-cell--auto">{s.auto_create ? 'Yes' : '—'}</span>
              <span className="sched-table__actions" onClick={(e) => e.stopPropagation()}>
                <button
                  className="sched-btn sched-btn--sm"
                  title="Enter now"
                  onClick={() => enter.mutate(s.id)}
                  disabled={enter.isPending}
                >
                  Enter
                </button>
                <button
                  className="sched-btn sched-btn--sm sched-btn--secondary"
                  title="Skip to next"
                  onClick={() => skip.mutate(s.id)}
                  disabled={skip.isPending}
                >
                  Skip
                </button>
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
