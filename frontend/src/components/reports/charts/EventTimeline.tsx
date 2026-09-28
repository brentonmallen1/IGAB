import { useMemo, useRef, useState } from 'react'
import { useReportStore } from '../../../stores/reportStore'
import { useTimelineReport } from '../../../api/reports'
import { usePayees } from '../../../api/payees'
import { useFormatters } from '../../../hooks/useFormatters'
import { ReportErrorState } from '../ReportErrorState'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ReportNotes } from '../ReportNotes'
import './EventTimeline.css'
import { useReportScope } from '../../../stores/reportStore'
import { drillScope } from '../drillScope'
import { activityClassTone } from '../../../utils/activityClassTone'
import { dotSize, largestMagnitude, newestFirst, timelineChip } from './timelineView'
import { TIMELINE_LIMITS } from './reportControls'
import { ReportHeader } from '../ReportHeader'

interface Props {
  budgetId: string
}

export function TimelineReport({ budgetId }: Props) {
  const { formatMoney, formatDate } = useFormatters()
  const { filters, setDrillDown } = useReportStore()
  const [limit, setLimit] = useState<(typeof TIMELINE_LIMITS)[number]>(25)
  // Money out by default: "the largest transactions" is read as where the
  // big money went, and a month of paycheques otherwise took most of the
  // slots. Inflows are one click away.
  const [outflowsOnly, setOutflowsOnly] = useState(true)
  const reportScope = useReportScope()
  const acctIds = filters.accountIds.length > 0 ? filters.accountIds : undefined
  const { data, isLoading, isError, error, refetch } = useTimelineReport(
    budgetId,
    filters.startDate,
    filters.endDate,
    limit,
    reportScope,
    acctIds,
    outflowsOnly
  )
  const { data: payees } = usePayees(budgetId)
  const captureRef = useRef<HTMLDivElement>(null)

  // Timeline rows carry names only — resolve back to ids for the drill-down
  const payeeIdByName = useMemo(() => new Map((payees ?? []).map((p) => [p.name, p.id])), [payees])

  const transactions = useMemo(() => newestFirst(data?.transactions ?? []), [data])

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  function drillTo(payeeName: string) {
    const payeeId = payeeIdByName.get(payeeName)
    if (!payeeId) return
    setDrillDown({
      kind: 'payee',
      label: payeeName,
      scope: 'parent',
      payeeIds: [payeeId],
      ...drillScope(reportScope),
      startDate: filters.startDate,
      endDate: filters.endDate,
    })
  }

  const largestAmt = largestMagnitude(transactions)

  return (
    <div className="report-section surface">
      <ReportHeader>
        <h2 className="report-section__title">Largest transactions</h2>
        <ReportInfoButton title="Largest transactions">
          <p>
            Your largest transactions in the period, drawn newest first. <strong>Money out</strong>{' '}
            lists outflows only; <strong>All</strong> lets deposits and refunds compete for the
            slots too. The <strong>dot size</strong> reflects the transaction&apos;s size relative
            to the largest in the set.
          </p>
          <p>
            Spending and income each have their own colour. Money moved into savings or used to pay
            down a tracked debt gets a colour and a label of its own — it left your budget, but it
            isn&apos;t spending. Amounts keep their sign: money out is negative, and money back into
            a spending category is marked <strong>Refund</strong>. Hover any dot for full details.
          </p>
          <ReportScopeNote report="timeline" />
        </ReportInfoButton>
        <p className="report-section__subtitle">
          Newest first; a dot&apos;s size is relative to the largest here.
        </p>
        <div className="flex-row ms-auto">
          <button
            className={`report-btn ${outflowsOnly ? 'report-btn--active' : ''}`}
            onClick={() => setOutflowsOnly(true)}
            type="button"
          >
            Money out
          </button>
          <button
            className={`report-btn ${!outflowsOnly ? 'report-btn--active' : ''}`}
            onClick={() => setOutflowsOnly(false)}
            type="button"
          >
            All
          </button>
          {TIMELINE_LIMITS.map((l) => (
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
                amount: tx.amount,
                memo: tx.memo ?? '',
              }))
            }
            captureRef={captureRef}
            window={{ start: filters.startDate, end: filters.endDate }}
          />
        </div>
      </ReportHeader>

      {/* The response declares `filter_unavailable`, and declaring it put
          nothing on screen: a deleted saved filter read as an empty period.
          Above the empty state, as on Day-of-Week, because it is the reason
          for it. No toggle here — the timeline counts every class. */}
      <ReportNotes report={data} toggleAvailable={false} />

      <div ref={captureRef} className="report-capture">
        {/* One card: "Shown: 25 transactions" restated the Top 25 button. */}
        {transactions.length > 0 && (
          <MetricRow>
            <MetricCard label="Largest" value={formatMoney(largestAmt)} />
          </MetricRow>
        )}

        {transactions.length === 0 ? (
          <div className="reports-empty">No transactions for this period.</div>
        ) : (
          <div className="timeline">
            <div className="timeline__track" />
            {transactions.map((tx, i) => {
              const amt = tx.amount
              const tone = activityClassTone(tx.activity_class)
              const size = dotSize(amt, largestAmt)
              const side = i % 2 === 0 ? 'left' : 'right'
              const chip = timelineChip(tx)
              return (
                <div key={tx.id} className={`timeline__event timeline__event--${side}`}>
                  <div
                    className={`timeline__dot timeline__dot--${tone}`}
                    style={{ width: size, height: size }}
                    title={`${formatDate(tx.date)} · ${tx.payee_name ?? 'Unknown'} · ${formatMoney(amt)}`}
                  />
                  <div
                    className={`timeline__card timeline__card--${side} ${tx.payee_name && payeeIdByName.has(tx.payee_name) ? 'timeline__card--clickable' : ''}`}
                    onClick={tx.payee_name ? () => drillTo(tx.payee_name!) : undefined}
                  >
                    <div className="timeline__date">{formatDate(tx.date)}</div>
                    <div className="timeline__payee">{tx.payee_name ?? 'Unknown Payee'}</div>
                    {tx.category_name && (
                      <div className="timeline__category">{tx.category_name}</div>
                    )}
                    <div className={`timeline__amount timeline__amount--${tone}`}>
                      {/* Signed: the tone is the class's, so without the
                        sign a refund read as a purchase of the same size. */}
                      {formatMoney(amt)}
                      {chip && <span className="timeline__class">{chip}</span>}
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
