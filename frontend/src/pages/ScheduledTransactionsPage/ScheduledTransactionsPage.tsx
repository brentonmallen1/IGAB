import { useState } from 'react'
import { useAppStore } from '../../stores/appStore'
import {
  useScheduledTransactions,
  useSkipScheduledTransaction,
  useEnterScheduledTransaction,
} from '../../api/scheduledTransactions'
import { useAccounts } from '../../api/accounts'
import { ScheduledTransactionEditor } from '../../components/scheduled/ScheduledTransactionEditor'
import { formatMoney } from '../../utils/money'
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
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data: scheduled = [] } = useScheduledTransactions(budgetId)
  const { data: accounts = [] } = useAccounts(budgetId)
  const skip = useSkipScheduledTransaction(budgetId ?? '')
  const enter = useEnterScheduledTransaction(budgetId ?? '')
  const [editing, setEditing] = useState<ScheduledTransaction | null | 'new'>(null)

  if (!budgetId) {
    return <div className="sched-page"><div className="sched-empty">Select a budget to view scheduled transactions.</div></div>
  }

  function accountName(id: string) {
    return accounts.find((a) => a.id === id)?.name ?? id
  }

  return (
    <div className="sched-page">
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
        <div className="sched-empty">No scheduled transactions. Create one to auto-post recurring bills.</div>
      ) : (
        <div className="sched-table">
          <div className="sched-table__head">
            <span>Account</span>
            <span>Amount</span>
            <span>Frequency</span>
            <span>Next Date</span>
            <span>Auto</span>
            <span></span>
          </div>
          {scheduled.map((s) => (
            <div key={s.id} className="sched-table__row" onClick={() => setEditing(s)}>
              <span>{accountName(s.account_id)}</span>
              <span className={Number(s.amount) < 0 ? 'negative' : 'positive'}>
                {formatMoney(Math.abs(Number(s.amount)))}
                {Number(s.amount) < 0 ? ' out' : ' in'}
              </span>
              <span>{FREQ_LABELS[s.frequency] ?? s.frequency}</span>
              <span>{s.next_occurrence_date}</span>
              <span>{s.auto_create ? 'Yes' : '—'}</span>
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
