import { useState } from 'react'
import {
  CartesianGrid, Legend, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { useBurnRateReport } from '../../../api/reports'
import { formatMoney } from '../../../utils/money'
import { ChartTooltip } from './ChartTooltip'
import { MetricCard } from '../MetricCard'
import { ReportInfoButton } from '../ReportInfoButton'

interface Props { budgetId: string }

export function BurnRateReport({ budgetId }: Props) {
  const [months, setMonths] = useState(12)
  const { data, isLoading } = useBurnRateReport(budgetId, months)

  if (isLoading) return <div className="report-loading">Loading…</div>

  const points = data?.points ?? []
  const latest = points[points.length - 1]

  const chartData = points.map((p) => ({
    date: p.date.slice(0, 7),
    '30-Day': Number(p.rolling_30),
    '90-Day Avg': Number(p.rolling_90),
  }))

  return (
    <div className="report-section">
      <div className="report-section__controls">
        <h2 className="report-section__title">Rolling Burn Rate</h2>
        <ReportInfoButton title="Rolling Burn Rate">
          <p>Shows your average monthly spending smoothed over <strong>30-day</strong> and <strong>90-day</strong> rolling windows.</p>
          <p>Rolling averages reduce calendar-month noise (e.g. quarterly bills). The 90-day line is more stable and better reflects your true spending rate. A widening gap between them signals recent spending changes.</p>
        </ReportInfoButton>
        <p className="report-section__subtitle" style={{ margin: 0 }}>Monthly spending rolling averages</p>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
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
        </div>
      </div>

      {latest && (
        <div className="report-metrics">
          <MetricCard label="Current 30-Day Burn" value={formatMoney(Number(latest.rolling_30))} />
          <MetricCard label="Current 90-Day Avg" value={formatMoney(Number(latest.rolling_90))} />
        </div>
      )}

      {chartData.length === 0 ? (
        <div className="reports-empty">No spending data available.</div>
      ) : (
        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} />
            <YAxis tickFormatter={(v) => formatMoney(v)} tick={{ fontSize: 11 }} width={90} />
            <Tooltip content={<ChartTooltip showTotal={false} />} offset={16} isAnimationActive={false} />
            <Legend />
            <Line type="monotone" dataKey="30-Day" stroke="#e15759" strokeWidth={2} dot={{ r: 3 }} />
            <Line type="monotone" dataKey="90-Day Avg" stroke="#4e79a7" strokeWidth={2} strokeDasharray="6 3" dot={{ r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
