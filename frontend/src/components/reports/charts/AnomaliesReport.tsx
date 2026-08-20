import { useState, useMemo } from 'react'
import { CheckCircle2 } from 'lucide-react'
import { LineChart, Line, ReferenceLine, ResponsiveContainer } from 'recharts'
import { useAnomaliesReport } from '../../../api/reports'
import { useReportStore } from '../../../stores/reportStore'
import { useFormatters } from '../../../hooks/useFormatters'
import { ReportErrorState } from '../ReportErrorState'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { Tooltip } from '../../common/Tooltip/Tooltip'

interface Props {
  budgetId: string
}

const MONTH_OPTIONS = [6, 12, 24] as const
const SENSITIVITY_OPTIONS = [
  { value: 3.0, label: 'Strict', description: 'z ≥ 3' },
  { value: 2.5, label: 'Normal', description: 'z ≥ 2.5' },
  { value: 2.0, label: 'Sensitive', description: 'z ≥ 2' },
] as const

export function AnomaliesReport({ budgetId }: Props) {
  const [months, setMonths] = useState<(typeof MONTH_OPTIONS)[number]>(12)
  const [threshold, setThreshold] = useState(2.5)
  const { data, isLoading, isError, refetch } = useAnomaliesReport(budgetId, months, threshold)
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
    // Parse month as YYYY-MM-DD and get start/end of that month
    const [year, month] = a.month.split('-').map(Number)
    const startDate = `${year}-${String(month).padStart(2, '0')}-01`
    const endOfMonth = new Date(year, month, 0) // day 0 of next month = last day of this month
    const endDate = `${year}-${String(month).padStart(2, '0')}-${String(endOfMonth.getDate()).padStart(2, '0')}`

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
  if (isError) return <ReportErrorState onRetry={() => refetch()} />

  return (
    <div className="report-section">
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
            <strong>Sensitivity</strong> controls the threshold: Strict shows only extreme
            outliers, Sensitive shows more subtle changes.
          </p>
          <ReportScopeNote scope="categories" />
        </ReportInfoButton>
        <div className="flex-row">
          {MONTH_OPTIONS.map((m) => (
            <button
              key={m}
              className={`report-btn ${months === m ? 'report-btn--active' : ''}`}
              onClick={() => setMonths(m)}
              type="button"
            >
              {m}mo
            </button>
          ))}
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
              <h3 className="anomalies-group__label">{monthLabel}</h3>
              {items.map((a) => {
                const actual = Number(a.actual)
                const baseline = Number(a.baseline_mean)
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
                        <span className="anomaly-card__baseline">
                          {formatMoney(baseline)}
                        </span>
                      </div>
                    </div>
                    <div className="anomaly-card__sparkline">
                      <ResponsiveContainer width={100} height={24}>
                        <LineChart data={a.history.map((v, i) => ({ i, v: Number(v) }))}>
                          <Line
                            type="monotone"
                            dataKey="v"
                            stroke={a.direction === 'high' ? 'var(--color-negative)' : 'var(--color-info)'}
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
