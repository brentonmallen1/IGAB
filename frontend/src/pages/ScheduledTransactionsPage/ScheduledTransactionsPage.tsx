import { PageHeader } from '../../components/common/PageHeader/PageHeader'
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
import {
  ScheduledRow,
  ScheduledTableHead,
} from '../../components/scheduled/ScheduledRow/ScheduledRow'
import type { ScheduledTransaction } from '../../types'
import { today } from '../../utils/dates'
import './ScheduledTransactionsPage.css'

export function ScheduledTransactionsPage() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data: scheduled = [] } = useScheduledTransactions(budgetId)
  const { data: accounts = [] } = useAccounts(budgetId)
  const { data: payees = [] } = usePayees(budgetId)
  const skip = useSkipScheduledTransaction(budgetId ?? '')
  const enter = useEnterScheduledTransaction(budgetId ?? '')
  const [editing, setEditing] = useState<ScheduledTransaction | null | 'new'>(null)
  const todayISO = today()

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
      <PageHeader
        title="Scheduled Transactions"
        actions={
          <button className="sched-btn sched-btn--primary" onClick={() => setEditing('new')}>
            + New
          </button>
        }
      />

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
          <ScheduledTableHead />
          {scheduled.map((s) => (
            <ScheduledRow
              key={s.id}
              scheduled={s}
              layout="table"
              todayISO={todayISO}
              names={{ payee: payeeName(s), account: accountName(s.account_id) }}
              onEdit={() => setEditing(s)}
              onEnter={() => enter.mutate(s.id)}
              onSkip={() => skip.mutate(s.id)}
              busy={enter.isPending || skip.isPending}
            />
          ))}
        </div>
      )}
    </div>
  )
}
