import { useRef, useState } from 'react'
import {
  CartesianGrid, Legend, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { useBurnRateReport } from '../../../api/reports'
import { useChartHeight } from '../../../hooks/useChartHeight'
import { useFormatters } from '../../../hooks/useFormatters'
import { ReportErrorState } from '../ReportErrorState'
import { ChartTooltip } from './ChartTooltip'
import { COLOR_NEGATIVE, COLOR_NEUTRAL } from './chartColors'
import { MetricCard } from '../MetricCard'
import { ReportInfoButton, ReportScopeNote, SpendingClassNote } from '../ReportInfoButton'
import { LogScaleToggle, logAxisProps } from './logScale'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'

interface Props { budgetId: string }

export function BurnRateReport({ budgetId }: Props) {
  const chartHeight = useChartHeight(320)
  const { formatMoney } = useFormatters()
  const [months, setMonths] = useState(12)
  const [logScale, setLogScale] = useState(false)
  const { data, isLoading, isError, refetch } = useBurnRateReport(budgetId, months)
  const captureRef = useRef<HTMLDivElement>(null)

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState onRetry={() => refetch()} />

  const points = data?.points ?? []
  const latest = points[points.length - 1]

  const chartData = points.map((p) => ({
    date: p.date.slice(0, 7),
    '30-Day': Number(p.rolling_30),
    '90-Day Avg': Number(p.rolling_90),
  }))

  return (
    <div className="report-section">
      <div className="report-section__header">
        <h2 className="report-section__title">Rolling Burn Rate</h2>
        <ReportInfoButton title="Rolling Burn Rate">
          <p>Shows your average monthly spending smoothed over <strong>30-day</strong> and <strong>90-day</strong> rolling windows.</p>
          <p>Rolling averages reduce calendar-month noise (e.g. quarterly bills). The 90-day line is more stable and better reflects your true spending rate. A widening gap between them signals recent spending changes.</p>
          <ReportScopeNote scope="on-budget" />
          <SpendingClassNote />
        </ReportInfoButton>
        <p className="report-section__subtitle">Monthly spending rolling averages</p>
        <div className="flex-row ms-auto">
          {([6, 12, 24] as const).map((m) => (
            <button
              key={m}
              className={`report-btn ${months === m ? 'report-btn--active' : ''}`}
              onClick={() => setMonths(m)}
              type="button"
            >
              {m}mo
            </button>
          ))}
          <LogScaleToggle enabled={logScale} onToggle={() => setLogScale((v) => !v)} />
          <ReportExportButton
            reportId="burn-rate"
            getRows={() =>
              points.map((p) => ({
                date: p.date,
                rolling_30: Number(p.rolling_30),
                rolling_90: Number(p.rolling_90),
              }))
            }
            captureRef={captureRef}
          />
        </div>
      </div>

      <div ref={captureRef} className="report-capture">
      {latest && (
        <div className="report-metrics">
          <MetricCard label="Current 30-Day Burn" value={formatMoney(Number(latest.rolling_30))} />
          <MetricCard label="Current 90-Day Avg" value={formatMoney(Number(latest.rolling_90))} />
        </div>
      )}

      {chartData.length === 0 ? (
        <div className="reports-empty">No spending data available.</div>
      ) : (
        <ResponsiveContainer width="100%" height={chartHeight}>
          <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
            <YAxis tickFormatter={(v) => formatMoney(v)} tick={{ fontSize: 11, fill: 'var(--text-muted)' }} width={90} {...logAxisProps(logScale)} />
            <Tooltip content={<ChartTooltip showTotal={false} />} offset={16} isAnimationActive={false} />
            <Legend />
            <Line type="monotone" dataKey="30-Day" stroke={COLOR_NEGATIVE} strokeWidth={2} dot={{ r: 3 }} />
            <Line type="monotone" dataKey="90-Day Avg" stroke={COLOR_NEUTRAL} strokeWidth={2} strokeDasharray="6 3" dot={{ r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      )}
      </div>
    </div>
  )
}
