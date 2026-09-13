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
  const { formatMoney, formatMonth } = useFormatters()

  const anomalies = useMemo(() => data?.anomalies ?? [], [data])

  const groupedByMonth = useMemo(() => {
    const groups = new Map<string, typeof anomalies>()
    for (const a of anomalies) {
      const monthKey = formatMonth(a.month)
      if (!groups.has(monthKey)) groups.set(monthKey, [])
      groups.get(monthKey)!.push(a)
    }
    return groups
  }, [anomalies, formatMonth])

  function handleClick(a: (typeof anomalies)[0]) {
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

  function getPercentChange(actual: number, baseline: number): string {
    if (baseline === 0) return actual > 0 ? '+∞%' : '0%'
    const pct = ((actual - baseline) / baseline) * 100
    const sign = pct >= 0 ? '+' : ''
    return `${sign}${Math.round(pct)}%`
  }

  function getTooltipContent(a: (typeof anomalies)[0]): React.ReactNode {
    const direction = a.direction === 'high' ? 'above' : 'below'
    return (
      <>
        z-score: {a.z_score.toFixed(1)}σ {direction} baseline
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
            This report surfaces <strong>unusual spending</strong> — category-months where your
            spending was significantly higher or lower than your baseline.
          </p>
          <p>
            Each anomaly shows the actual amount vs. your typical spending, with a{' '}
            <strong>percentage change</strong> indicating how much it differs from normal.
          </p>
          <p>
            <strong>Sensitivity</strong> controls the threshold: Strict shows only extreme outliers,
            Sensitive shows more subtle changes.
          </p>
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
          <p className="anomalies-empty__sub">
            Your spending patterns look normal for this period.
          </p>
        </div>
      ) : (
        <div className="anomalies-list">
          {[...groupedByMonth.entries()].map(([monthLabel, items]) => (
            <div key={monthLabel} className="anomalies-group">
              {/* Every row in a group shares a month, so the first one says
                  whether it is still being written. `partial_month` is the
                  server's — see AnomalyItem in types/index.ts. */}
              <h3 className="anomalies-group__label">
                {monthLabel}
                {items[0].partial_month && (
                  <span className="anomalies-group__partial">so far this month</span>
                )}
              </h3>
              {items.map((a) => {
                const actual = a.actual
                const baseline = a.baseline_mean
                const pctChange = getPercentChange(actual, baseline)

                return (
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
                        <span
                          className={`anomaly-card__actual anomaly-card__actual--${a.direction}`}
                        >
                          {formatMoney(actual)}
                        </span>
                        <span className="anomaly-card__vs">vs usual</span>
                        <span className="anomaly-card__baseline">{formatMoney(baseline)}</span>
                      </div>
                    </div>
                    <div className="anomaly-card__sparkline">
                      <ResponsiveContainer width={100} height={24}>
                        <LineChart data={a.history.map((v, i) => ({ i, v: v }))}>
                          <Line
                            type="monotone"
                            dataKey="v"
                            stroke={
                              a.direction === 'high' ? 'var(--color-negative)' : 'var(--color-info)'
                            }
                            strokeWidth={1.5}
                            dot={false}
                          />
                          <ReferenceLine
                            y={baseline}
                            stroke="var(--text-muted)"
                            strokeDasharray="2 2"
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                    <Tooltip content={getTooltipContent(a)}>
                      <span className={`anomaly-card__pct anomaly-card__pct--${a.direction}`}>
                        {pctChange}
                      </span>
                    </Tooltip>
                  </button>
                )
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
