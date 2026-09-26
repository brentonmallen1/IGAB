import { useState, useMemo } from 'react'
import { CheckCircle2 } from 'lucide-react'
import { LineChart, Line, ReferenceLine, ResponsiveContainer } from 'recharts'
import { useAnomaliesReport } from '../../../api/reports'
import { useReportMonths, useReportStore } from '../../../stores/reportStore'
import { useFormatters } from '../../../hooks/useFormatters'
import { ReportErrorState } from '../ReportErrorState'
import { ReportRangeSelect } from './rangeSelect'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { Tooltip } from '../../common/Tooltip/Tooltip'
import { monthWindow } from '../../../utils/dateWindow'
import { SENSITIVITY_OPTIONS } from './reportControls'
import { groupByMonthNewestFirst, percentChange, testedLine } from './anomaliesView'
import type { AnomalyItem } from '../../../types'

interface Props {
  budgetId: string
}

export function AnomaliesReport({ budgetId }: Props) {
  const months = useReportMonths()
  const [threshold, setThreshold] = useState(2.5)
  const { data, isLoading, isError, error, refetch } = useAnomaliesReport(
    budgetId,
    months,
    threshold
  )
  const { setDrillDown } = useReportStore()
  const { formatMoney, formatMonthShort } = useFormatters()

  const anomalies = useMemo(() => data?.anomalies ?? [], [data])
  const groups = useMemo(() => groupByMonthNewestFirst(anomalies), [anomalies])

  function handleClick(a: AnomalyItem) {
    // monthWindow clamps the end to today, which this copy did not: for the
    // current month it asked for days that have not happened, so the panel
    // could total more than the card that opened it.
    const { start: startDate, end: endDate } = monthWindow(a.month)

    setDrillDown({
      kind: 'category',
      label: a.category_name,
      scope: 'leaf',
      direction: 'outflow',
      categoryIds: [a.category_id],
      startDate,
      endDate,
    })
  }

  function tooltipContent(a: AnomalyItem): React.ReactNode {
    const direction = a.direction === 'high' ? 'above' : 'below'
    return (
      <>
        {Math.abs(a.z_score).toFixed(1)}σ {direction} the average of the months before it (
        {formatMoney(a.baseline_mean)})
      </>
    )
  }

  if (isLoading) {
    return <div className="report-loading">Loading...</div>
  }
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Spending Anomalies</h2>
        <ReportInfoButton title="Spending Anomalies">
          <p>
            Category-months whose spending sat well outside what the category usually spends, judged
            against the <strong>months before</strong> — at least six of them. A month with nothing
            spent counts as zero, and refunds lower a month.
          </p>
          <p>
            &ldquo;Usually&rdquo; is the average of those months one standard deviation (σ) either
            way. <strong>Sensitivity</strong> is how many σ away a month must be: Strict 3, Normal
            2.5, Sensitive 2. The month in progress is only flagged when it is already high.
          </p>
          <p>Sinking funds (Long-term expense) are not tested: their bills are the plan.</p>
          <ReportScopeNote report="anomalies" />
        </ReportInfoButton>
        <div className="flex-row">
          <ReportRangeSelect />
        </div>
        <div className="flex-row">
          {SENSITIVITY_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              className={`report-btn ${threshold === opt.value ? 'report-btn--active' : ''}`}
              onClick={() => setThreshold(opt.value)}
              type="button"
              title={opt.description}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {anomalies.length === 0 ? (
        <div className="anomalies-empty">
          <CheckCircle2 size={48} strokeWidth={1.5} />
          <p>No unusual spending detected</p>
          {data && <p className="anomalies-empty__sub">{testedLine(data)}</p>}
        </div>
      ) : (
        <div className="anomalies-list">
          {groups.map(({ month, items }) => (
            <div key={month} className="anomalies-group">
              {/* Every row in a group shares a month, so the first one says
                  whether it is still being written. `partial_month` is the
                  server's — see AnomalyItem in types/index.ts. */}
              <h3 className="anomalies-group__label">
                {formatMonthShort(month)}
                {/* "Sep 26 so far", as `reportMonthLabel` says it everywhere
                    else; a span so the caveat is not set as a heading. */}
                {items[0].partial_month && <span className="anomalies-group__partial">so far</span>}
              </h3>
              {items.map((a) => (
                <button
                  key={`${a.category_id}-${a.month}`}
                  className="anomaly-card"
                  onClick={() => handleClick(a)}
                  type="button"
                >
                  <div className="anomaly-card__main">
                    <div className="anomaly-card__category">
                      <span className="anomaly-card__name">{a.category_name}</span>
                      <span className="anomaly-card__group">{a.group_name}</span>
                    </div>
                    <div className="anomaly-card__description">
                      <span className={`anomaly-card__actual anomaly-card__actual--${a.direction}`}>
                        {formatMoney(a.actual)}
                      </span>
                      <span className="anomaly-card__vs">usually</span>
                      <span className="anomaly-card__baseline">
                        {formatMoney(a.usual_low)}–{formatMoney(a.usual_high)}
                      </span>
                    </div>
                  </div>
                  <div className="anomaly-card__sparkline" aria-hidden="true">
                    {/* Calendar months: a quiet month is a zero on the line,
                        a month before the category's first spending a gap. */}
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={a.history.map((v, i) => ({ i, v }))}>
                        <Line
                          type="linear"
                          dataKey="v"
                          stroke={
                            a.direction === 'high' ? 'var(--color-negative)' : 'var(--color-info)'
                          }
                          strokeWidth={1.5}
                          dot={false}
                          connectNulls={false}
                          isAnimationActive={false}
                        />
                        <ReferenceLine
                          y={a.baseline_mean}
                          stroke="var(--text-muted)"
                          strokeDasharray="2 2"
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                  <Tooltip content={tooltipContent(a)}>
                    <span className={`anomaly-card__pct anomaly-card__pct--${a.direction}`}>
                      {percentChange(a.actual, a.baseline_mean)}
                    </span>
                  </Tooltip>
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
