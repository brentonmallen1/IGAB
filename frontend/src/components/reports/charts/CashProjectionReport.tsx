import { useState } from 'react'
import {
  Area,
  ComposedChart,
  CartesianGrid,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { AlertTriangle, Calendar } from 'lucide-react'
import { useCashProjectionReport } from '../../../api/reports'
import { useChartHeight } from '../../../hooks/useChartHeight'
import { useFormatters } from '../../../hooks/useFormatters'
import { useMoneyAxis } from '../../../hooks/useMoneyAxis'
import { ReportErrorState } from '../ReportErrorState'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ChartTooltip } from './ChartTooltip'
import {
  MEDIAN_LABEL,
  PROJECTION_BANDS,
  SCHEDULED_LABEL,
  projectionRows,
  projectionTooltipEntries,
  projectionWarning,
  type ProjectionRow,
} from './cashProjectionView'
import { HORIZON_OPTIONS } from './reportControls'

interface Props {
  budgetId: string
}

export function CashProjectionReport({ budgetId }: Props) {
  const chartHeight = useChartHeight(360)
  const [horizon, setHorizon] = useState<(typeof HORIZON_OPTIONS)[number]>(90)
  const { data, isLoading, isError, error, refetch } = useCashProjectionReport(budgetId, horizon)
  const { formatMoney, formatDate, formatDayMonth } = useFormatters()
  const moneyAxis = useMoneyAxis()

  if (isLoading) {
    return <div className="report-loading">Loading...</div>
  }
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  const events = data?.events ?? []
  const startBalance = Number(data?.start_balance ?? 0)
  const warning = projectionWarning(data)

  const chartData = projectionRows(data?.points ?? [], formatDayMonth)

  const endPoint = chartData[chartData.length - 1]
  const projectedBalance = endPoint?.p50 ?? startBalance
  const rangeP10 = endPoint?.p10 ?? startBalance
  const rangeP90 = endPoint?.p90 ?? startBalance

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Cash Projection</h2>
        <ReportInfoButton title="Cash Projection">
          <p>
            Where your cash balance lands <strong>if things carry on</strong>: your recent cash in
            and out — paychecks included — replayed on top of your scheduled transactions and
            subscriptions.
          </p>
          <p>
            Each simulated path copies stretches of your real history a few weeks at a time, so
            weekends and paydays keep their places. The <strong>solid line</strong> is the{' '}
            {MEDIAN_LABEL.toLowerCase()}: half the paths end above it, half below. The darker band
            holds the <strong>middle half</strong> of the paths (25–75%); the lighter band holds{' '}
            <strong>8 in 10</strong> (10–90%) — 1 in 10 ends below it, 1 in 10 above.
          </p>
          <p>
            The <strong>dashed line</strong> shows what would happen with only scheduled and
            subscription charges — no random daily spending.
          </p>
          <ReportScopeNote report="projection" />
        </ReportInfoButton>
        <div className="flex-row">
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

      {warning && (
        <div
          className={`projection-warning${warning.kind === 'possible' ? ' projection-warning--possible' : ''}`}
        >
          <AlertTriangle size={16} />
          <span>
            {warning.lead} {formatMoney(0)} by <strong>{formatDate(warning.date)}</strong>
          </span>
        </div>
      )}

      <MetricRow>
        <MetricCard label="Current Balance" value={formatMoney(startBalance)} />
        <MetricCard
          label={`Projected (${horizon}d)`}
          value={formatMoney(projectedBalance)}
          sub={`8 in 10: ${formatMoney(rangeP10)} – ${formatMoney(rangeP90)}`}
        />
      </MetricRow>

      {chartData.length === 0 ? (
        <div className="reports-empty">No projection data available.</div>
      ) : (
        <ResponsiveContainer width="100%" height={chartHeight}>
          <ComposedChart data={chartData} margin={{ top: 8, right: 20, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
              interval={Math.floor(chartData.length / 8)}
            />
            <YAxis
              tickFormatter={moneyAxis.tickFormatter}
              tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
              width={moneyAxis.width}
            />
            {warning && <ReferenceLine y={0} stroke="var(--color-negative)" strokeWidth={1} />}
            <Tooltip
              content={({ active, payload, label }) => (
                <ChartTooltip
                  active={active}
                  payload={
                    payload?.length
                      ? projectionTooltipEntries(payload[0].payload as ProjectionRow)
                      : []
                  }
                  label={String(label ?? '')}
                  formatter={formatMoney}
                />
              )}
              offset={16}
              isAnimationActive={false}
            />
            {/* Range areas: each band is its own [low, high], unstacked, so the
                shading is the band and the axis spans the real values. */}
            <Area
              type="monotone"
              dataKey="outer"
              name={PROJECTION_BANDS.outer.label}
              stroke="none"
              fill="var(--accent-color)"
              fillOpacity={PROJECTION_BANDS.outer.fillOpacity}
              isAnimationActive={false}
            />
            <Area
              type="monotone"
              dataKey="inner"
              name={PROJECTION_BANDS.inner.label}
              stroke="none"
              fill="var(--accent-color)"
              fillOpacity={PROJECTION_BANDS.inner.fillOpacity}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="deterministic"
              name={SCHEDULED_LABEL}
              stroke="var(--text-muted)"
              strokeDasharray="4 4"
              strokeWidth={1.5}
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="p50"
              name={MEDIAN_LABEL}
              stroke="var(--accent-color)"
              strokeWidth={2}
              dot={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      )}

      {chartData.length > 0 && (
        <div className="chart-key">
          {[PROJECTION_BANDS.inner, PROJECTION_BANDS.outer].map((band) => (
            <span key={band.label} className="chart-key__item">
              <span
                className="chart-key__swatch"
                style={{ background: 'var(--accent-color)', opacity: band.swatchOpacity }}
              />
              {band.label}
            </span>
          ))}
          <span className="chart-key__item">
            <span
              className="chart-key__swatch chart-key__swatch--line"
              style={{ background: 'var(--accent-color)' }}
            />
            {MEDIAN_LABEL}
          </span>
          <span className="chart-key__item">
            <span
              className="chart-key__swatch chart-key__swatch--line"
              style={{ background: 'var(--text-muted)' }}
            />
            {SCHEDULED_LABEL}
          </span>
        </div>
      )}

      {events.length > 0 && (
        <div className="projection-events">
          <h3 className="projection-events__title">Upcoming Events (next 30 days)</h3>
          <div className="projection-events__list">
            {events.map((e, i) => (
              <div key={i} className="projection-event">
                <Calendar size={14} className="projection-event__icon" />
                <span className="projection-event__date">{formatDayMonth(e.date)}</span>
                <span className="projection-event__payee">{e.payee}</span>
                <span
                  className={`projection-event__amount ${e.amount >= 0 ? 'projection-event__amount--positive' : ''}`}
                >
                  {formatMoney(e.amount)}
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
