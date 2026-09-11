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

/** Dot colour by what a row means, not which way the amount points.
 *
 * A null class is a split whose legs disagree, and it gets the neutral tone
 * rather than a sign-based guess — falling back to the sign is the exact
 * mislabelling the activity taxonomy exists to end, and it is how an
 * all-savings split came to be drawn as a red expense.
 */
const TONE_BY_CLASS: Record<string, string> = {
  income: 'income',
  spending: 'expense',
  savings: 'savings',
  debt_principal: 'savings',
  investment_return: 'neutral',
  debt_interest: 'expense',
  transfer_internal: 'neutral',
}

interface Props {
  budgetId: string
}

const LIMITS = [25, 50, 100] as const

export function TimelineReport({ budgetId }: Props) {
  const { formatMoney } = useFormatters()
  const { filters, setDrillDown } = useReportStore()
  const [limit, setLimit] = useState<25 | 50 | 100>(25)
  const reportScope = useReportScope()
  const acctIds = filters.accountIds.length > 0 ? filters.accountIds : undefined
  const { data, isLoading, isError, error, refetch } = useTimelineReport(
    budgetId,
    filters.startDate,
    filters.endDate,
    limit,
    reportScope,
    acctIds
  )
  const { data: payees } = usePayees(budgetId)
  const captureRef = useRef<HTMLDivElement>(null)

  // Timeline rows carry names only — resolve back to ids for the drill-down
  const payeeIdByName = useMemo(() => new Map((payees ?? []).map((p) => [p.name, p.id])), [payees])

  // The server ranks by SIZE to pick the largest N; a timeline draws them in
  // DATE order. The panel has been saying "displayed chronologically" while
  // rendering the server's ranking, so the newest row could appear anywhere.
  const transactions = useMemo(
    () => [...(data?.transactions ?? [])].sort((a, b) => b.date.localeCompare(a.date)),
    [data]
  )

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

  // Taken from the whole page rather than from row 0. The server ranks by size
  // now, so row 0 IS the largest — but a scale that silently depends on the
  // sort order is how this came to be wrong in the first place, and a max over
  // the rows cannot be.
  const largestAmt = transactions.reduce((m, t) => Math.max(m, Math.abs(t.amount)), 0)

  const dotSize = (amount: number) => {
    if (largestAmt === 0) return 8
    const t = Math.abs(amount) / largestAmt
    return Math.round(8 + t * 14)
  }

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Event Timeline</h2>
        <ReportInfoButton title="Event Timeline">
          <p>
            Your largest transactions, newest first. The <strong>dot size</strong> reflects the
            transaction's magnitude relative to the largest in the set — bigger dot = larger amount.
          </p>
          <p>
            <strong>Red dots</strong> are spending; <strong>green dots</strong> are income. Money
            moved into savings or used to pay down a tracked debt gets its own colour and a label —
            it left your budget, but it isn't spending. Transactions alternate left/right for
            readability. Hover any dot for full details.
          </p>
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
                amount: tx.amount,
                memo: tx.memo ?? '',
              }))
            }
            captureRef={captureRef}
            window={{ start: filters.startDate, end: filters.endDate }}
          />
        </div>
      </div>

      {/* The response declares `filter_unavailable`, and declaring it put
          nothing on screen: a deleted saved filter read as an empty period.
          Above the empty state, as on Day-of-Week, because it is the reason
          for it. No toggle here — the timeline counts every class. */}
      <ReportNotes report={data} toggleAvailable={false} />

      <div ref={captureRef} className="report-capture">
        {transactions.length > 0 && (
          <MetricRow>
            <MetricCard label="Largest Transaction" value={formatMoney(largestAmt)} />
            <MetricCard label="Shown" value={`${transactions.length} transactions`} />
          </MetricRow>
        )}

        {transactions.length === 0 ? (
          <div className="reports-empty">No transactions for this period.</div>
        ) : (
          <div className="timeline">
            <div className="timeline__track" />
            {transactions.map((tx, i) => {
              const amt = tx.amount
              // By class, not by sign. A transfer into savings is negative but is
              // not an expense, and drawing it red said otherwise.
              const tone = tx.activity_class
                ? (TONE_BY_CLASS[tx.activity_class] ?? 'neutral')
                : 'neutral'
              const size = dotSize(amt)
              const side = i % 2 === 0 ? 'left' : 'right'
              return (
                <div key={tx.id} className={`timeline__event timeline__event--${side}`}>
                  <div
                    className={`timeline__dot timeline__dot--${tone}`}
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
                    <div className={`timeline__amount timeline__amount--${tone}`}>
                      {formatMoney(Math.abs(amt))}
                      {/* Label served with the row, so a class added later
                        cannot silently lose its chip here. */}
                      {tx.activity_class !== 'spending' && (
                        <span className="timeline__class">{tx.activity_label}</span>
                      )}
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
