import { useState } from 'react'
import {
  Area, ComposedChart, CartesianGrid, Line, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { AlertTriangle, Calendar } from 'lucide-react'
import { useCashProjectionReport } from '../../../api/reports'
import { formatMoney } from '../../../utils/money'
import { MetricCard } from '../MetricCard'
import { ReportInfoButton } from '../ReportInfoButton'

interface Props {
  budgetId: string
}

const HORIZON_OPTIONS = [30, 60, 90, 180] as const

export function CashProjectionReport({ budgetId }: Props) {
  const [horizon, setHorizon] = useState<(typeof HORIZON_OPTIONS)[number]>(90)
  const { data, isLoading } = useCashProjectionReport(budgetId, horizon)

  if (isLoading) {
    return <div className="report-loading">Loading...</div>
  }

  const points = data?.points ?? []
  const events = data?.events ?? []
  const startBalance = Number(data?.start_balance ?? 0)
  const goesNegativeDate = data?.goes_negative_date

  const chartData = points.map((p) => ({
    date: new Date(p.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    fullDate: p.date,
    p10: Number(p.p10),
    p25: Number(p.p25),
    p50: Number(p.p50),
    p75: Number(p.p75),
    p90: Number(p.p90),
    deterministic: Number(p.deterministic),
  }))

  const endPoint = chartData[chartData.length - 1]
  const projectedBalance = endPoint?.p50 ?? startBalance
  const rangeP10 = endPoint?.p10 ?? startBalance
  const rangeP90 = endPoint?.p90 ?? startBalance

  return (
    <div className="report-section">
      <div className="report-section__controls">
        <h2 className="report-section__title">Cash Projection</h2>
        <ReportInfoButton title="Cash Projection">
          <p>
            Projects your <strong>future cash balance</strong> based on scheduled transactions,
            subscription patterns, and historical spending variability.
          </p>
          <p>
            The <strong>solid line</strong> shows the median projection (P50). The{' '}
            <strong>shaded bands</strong> show uncertainty — inner band (25-75%) represents the
            likely range, outer band (10-90%) covers most scenarios.
          </p>
          <p>
            The <strong>dashed line</strong> shows what would happen with only scheduled and
            subscription charges — no random daily spending.
          </p>
        </ReportInfoButton>
        <div className="report-section__controls" style={{ gap: 4, marginLeft: 'var(--spacing-md)' }}>
          {HORIZON_OPTIONS.map((h) => (
            <button
              key={h}
              className={`report-btn ${horizon === h ? 'report-btn--active' : ''}`}
              onClick={() => setHorizon(h)}
              type="button"
            >
              {h}d
            </button>
          ))}
        </div>
      </div>

      {goesNegativeDate && (
        <div className="projection-warning">
          <AlertTriangle size={16} />
          <span>
            Projection goes negative around{' '}
            <strong>
              {new Date(goesNegativeDate).toLocaleDateString('en-US', {
                month: 'long',
                day: 'numeric',
              })}
            </strong>
          </span>
        </div>
      )}

      <div className="report-metrics">
        <MetricCard label="Current Balance" value={formatMoney(startBalance)} />
        <MetricCard
          label={`Projected (${horizon}d)`}
          value={formatMoney(projectedBalance)}
          sub={`Range: ${formatMoney(rangeP10)} – ${formatMoney(rangeP90)}`}
        />
      </div>

      {chartData.length === 0 ? (
        <div className="reports-empty">No projection data available.</div>
      ) : (
        <ResponsiveContainer width="100%" height={360}>
          <ComposedChart data={chartData} margin={{ top: 8, right: 20, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11 }}
              interval={Math.floor(chartData.length / 8)}
            />
            <YAxis tickFormatter={(v) => formatMoney(v)} tick={{ fontSize: 11 }} width={80} />
            {goesNegativeDate && (
              <ReferenceLine y={0} stroke="var(--color-negative)" strokeWidth={1} />
            )}
            <Tooltip
              formatter={(v: unknown, name: unknown) => {
                const label =
                  name === 'p50'
                    ? 'Median'
                    : name === 'deterministic'
                      ? 'Scheduled Only'
                      : String(name)
                return [formatMoney(Number(v)), label]
              }}
              labelFormatter={(label) => `${label}`}
              offset={16}
              isAnimationActive={false}
            />
            {/* Outer band P10-P90 */}
            <Area
              type="monotone"
              dataKey="p90"
              stackId="band-outer"
              stroke="none"
              fill="var(--accent-color)"
              fillOpacity={0.08}
            />
            <Area
              type="monotone"
              dataKey="p10"
              stackId="band-outer"
              stroke="none"
              fill="var(--bg-primary)"
              fillOpacity={1}
            />
            {/* Inner band P25-P75 */}
            <Area
              type="monotone"
              dataKey="p75"
              stackId="band-inner"
              stroke="none"
              fill="var(--accent-color)"
              fillOpacity={0.15}
            />
            <Area
              type="monotone"
              dataKey="p25"
              stackId="band-inner"
              stroke="none"
              fill="var(--bg-primary)"
              fillOpacity={1}
            />
            {/* Deterministic line */}
            <Line
              type="monotone"
              dataKey="deterministic"
              stroke="var(--text-muted)"
              strokeDasharray="4 4"
              strokeWidth={1.5}
              dot={false}
            />
            {/* Median line */}
            <Line
              type="monotone"
              dataKey="p50"
              stroke="var(--accent-color)"
              strokeWidth={2}
              dot={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      )}

      {events.length > 0 && (
        <div className="projection-events">
          <h3 className="projection-events__title">Upcoming Events (next 30 days)</h3>
          <div className="projection-events__list">
            {events.map((e, i) => (
              <div key={i} className="projection-event">
                <Calendar size={14} className="projection-event__icon" />
                <span className="projection-event__date">
                  {new Date(e.date).toLocaleDateString('en-US', {
                    month: 'short',
                    day: 'numeric',
                  })}
                </span>
                <span className="projection-event__payee">{e.payee}</span>
                <span
                  className={`projection-event__amount ${Number(e.amount) >= 0 ? 'projection-event__amount--positive' : ''}`}
                >
                  {formatMoney(Number(e.amount))}
                </span>
                <span className={`projection-event__source projection-event__source--${e.source}`}>
                  {e.source}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
