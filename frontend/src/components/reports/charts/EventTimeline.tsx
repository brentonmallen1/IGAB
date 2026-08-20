import { useMemo, useRef, useState } from 'react'
import { useReportStore } from '../../../stores/reportStore'
import { useTimelineReport } from '../../../api/reports'
import { usePayees } from '../../../api/payees'
import { useFormatters } from '../../../hooks/useFormatters'
import { ReportErrorState } from '../ReportErrorState'
import { MetricCard } from '../MetricCard'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import './EventTimeline.css'

interface Props { budgetId: string }

const LIMITS = [25, 50, 100] as const

export function TimelineReport({ budgetId }: Props) {
  const { formatMoney } = useFormatters()
  const { filters, setDrillDown } = useReportStore()
  const [limit, setLimit] = useState<25 | 50 | 100>(25)
  const catIds = filters.categoryIds.length > 0 ? filters.categoryIds : undefined
  const acctIds = filters.accountIds.length > 0 ? filters.accountIds : undefined
  const { data, isLoading, isError, refetch } = useTimelineReport(budgetId, filters.startDate, filters.endDate, limit, catIds, acctIds)
  const { data: payees } = usePayees(budgetId)
  const captureRef = useRef<HTMLDivElement>(null)

  // Timeline rows carry names only — resolve back to ids for the drill-down
  const payeeIdByName = useMemo(
    () => new Map((payees ?? []).map((p) => [p.name, p.id])),
    [payees],
  )

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState onRetry={() => refetch()} />

  function drillTo(payeeName: string) {
    const payeeId = payeeIdByName.get(payeeName)
    if (!payeeId) return
    setDrillDown({
      kind: 'payee', label: payeeName, scope: 'parent',
      payeeIds: [payeeId], startDate: filters.startDate, endDate: filters.endDate,
    })
  }

  const transactions = data?.transactions ?? []
  const largestAmt = transactions.length > 0 ? Math.abs(Number(transactions[0].amount)) : 0

  const dotSize = (amount: number) => {
    if (largestAmt === 0) return 8
    const t = Math.abs(amount) / largestAmt
    return Math.round(8 + t * 14)
  }

  return (
    <div className="report-section">
      <div className="report-section__header">
        <h2 className="report-section__title">Event Timeline</h2>
        <ReportInfoButton title="Event Timeline">
          <p>Your largest transactions displayed chronologically. The <strong>dot size</strong> reflects the transaction's magnitude relative to the largest in the set — bigger dot = larger amount.</p>
          <p><strong>Red dots</strong> are expenses; <strong>green dots</strong> are income. Transactions alternate left/right for readability. Hover any dot for full details.</p>
          <ReportScopeNote scope="on-budget-filterable" />
        </ReportInfoButton>
        <p className="report-section__subtitle">
          Largest transactions — size indicates relative magnitude.
        </p>
        <div className="flex-row ms-auto">
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
          <ReportExportButton
            reportId="timeline"
            getRows={() =>
              transactions.map((tx) => ({
                date: tx.date,
                payee: tx.payee_name ?? '',
                category: tx.category_name ?? '',
                amount: Number(tx.amount),
                memo: tx.memo ?? '',
              }))
            }
            captureRef={captureRef}
            window={{ start: filters.startDate, end: filters.endDate }}
          />
        </div>
      </div>

      <div ref={captureRef} className="report-capture">
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
                <div
                  className={`timeline__card timeline__card--${side} ${tx.payee_name && payeeIdByName.has(tx.payee_name) ? 'timeline__card--clickable' : ''}`}
                  onClick={tx.payee_name ? () => drillTo(tx.payee_name!) : undefined}
                >
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
    </div>
  )
}
