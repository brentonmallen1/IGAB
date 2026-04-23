import { useState } from 'react'
import { useReportStore } from '../../../stores/reportStore'
import { useTimelineReport } from '../../../api/reports'
import { formatMoney } from '../../../utils/money'
import { MetricCard } from '../MetricCard'
import { ReportInfoButton } from '../ReportInfoButton'
import './EventTimeline.css'

interface Props { budgetId: string }

const LIMITS = [25, 50, 100] as const

export function TimelineReport({ budgetId }: Props) {
  const { filters } = useReportStore()
  const [limit, setLimit] = useState<25 | 50 | 100>(25)
  const catIds = filters.categoryIds.length > 0 ? filters.categoryIds : undefined
  const acctIds = filters.accountIds.length > 0 ? filters.accountIds : undefined
  const { data, isLoading } = useTimelineReport(budgetId, filters.startDate, filters.endDate, limit, catIds, acctIds)

  if (isLoading) return <div className="report-loading">Loading…</div>

  const transactions = data?.transactions ?? []
  const largestAmt = transactions.length > 0 ? Math.abs(Number(transactions[0].amount)) : 0

  const dotSize = (amount: number) => {
    if (largestAmt === 0) return 8
    const t = Math.abs(amount) / largestAmt
    return Math.round(8 + t * 14)
  }

  return (
    <div className="report-section">
      <div className="report-section__controls">
        <h2 className="report-section__title">Event Timeline</h2>
        <ReportInfoButton title="Event Timeline">
          <p>Your largest transactions displayed chronologically. The <strong>dot size</strong> reflects the transaction's magnitude relative to the largest in the set — bigger dot = larger amount.</p>
          <p><strong>Red dots</strong> are expenses; <strong>green dots</strong> are income. Transactions alternate left/right for readability. Hover any dot for full details.</p>
        </ReportInfoButton>
        <p className="report-section__subtitle" style={{ margin: 0 }}>
          Largest transactions — size indicates relative magnitude.
        </p>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          {LIMITS.map((l) => (
            <button
              key={l}
              className={`report-btn ${limit === l ? 'report-btn--active' : ''}`}
              onClick={() => setLimit(l)}
              type="button"
            >
              Top {l}
            </button>
          ))}
        </div>
      </div>

      {transactions.length > 0 && (
        <div className="report-metrics">
          <MetricCard label="Largest Transaction" value={formatMoney(largestAmt)} />
          <MetricCard label="Shown" value={`${transactions.length} transactions`} />
        </div>
      )}

      {transactions.length === 0 ? (
        <div className="reports-empty">No transactions for this period.</div>
      ) : (
        <div className="timeline">
          <div className="timeline__track" />
          {transactions.map((tx, i) => {
            const amt = Number(tx.amount)
            const isExpense = amt < 0
            const size = dotSize(amt)
            const side = i % 2 === 0 ? 'left' : 'right'
            return (
              <div key={tx.id} className={`timeline__event timeline__event--${side}`}>
                <div
                  className={`timeline__dot ${isExpense ? 'timeline__dot--expense' : 'timeline__dot--income'}`}
                  style={{ width: size, height: size }}
                  title={`${tx.date} · ${tx.payee_name ?? 'Unknown'} · ${formatMoney(Math.abs(amt))}`}
                />
                <div className={`timeline__card timeline__card--${side}`}>
                  <div className="timeline__date">{tx.date}</div>
                  <div className="timeline__payee">{tx.payee_name ?? 'Unknown Payee'}</div>
                  {tx.category_name && (
                    <div className="timeline__category">{tx.category_name}</div>
                  )}
                  <div className={`timeline__amount ${isExpense ? 'timeline__amount--expense' : 'timeline__amount--income'}`}>
                    {formatMoney(Math.abs(amt))}
                  </div>
                  {tx.memo && <div className="timeline__memo">{tx.memo}</div>}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
