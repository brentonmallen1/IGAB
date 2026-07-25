import { useRef, useState } from 'react'
import {
  Bar, ComposedChart, CartesianGrid, Legend, Line,
  ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { useVarianceReport } from '../../../api/reports'
import { formatMoney } from '../../../utils/money'
import { ChartTooltip } from './ChartTooltip'
import { MetricCard } from '../MetricCard'
import { ReportInfoButton } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'

interface Props { budgetId: string }

export function VarianceReport({ budgetId }: Props) {
  const [months, setMonths] = useState(12)
  const { data, isLoading } = useVarianceReport(budgetId, months)
  const captureRef = useRef<HTMLDivElement>(null)

  if (isLoading) return <div className="report-loading">Loading…</div>

  const points = data?.points ?? []
  const latest = points[points.length - 1]

  const chartData = points.map((p) => ({
    month: p.month.slice(0, 7),
    Assigned: Number(p.budget_assigned),
    Spent: Number(p.actual_spent),
    'Monthly Variance': Number(p.monthly_variance),
    'Cumulative': Number(p.cumulative_variance),
  }))

  return (
    <div className="report-section">
      <div className="report-section__controls">
        <h2 className="report-section__title">Cumulative Budget Variance</h2>
        <ReportInfoButton title="Cumulative Budget Variance">
          <p>Tracks the <strong>running total of assigned minus spent</strong> across all months. Positive = you've been consistently under budget; negative = you've been consistently over.</p>
          <p>The <strong>bars</strong> show the monthly assigned vs spent gap. The <strong>line</strong> is the cumulative drift — if it slopes down, your budget is eroding month by month.</p>
        </ReportInfoButton>
        <p className="report-section__subtitle" style={{ margin: 0 }}>Running budget drift over time</p>
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
          <ReportExportButton
            reportId="variance"
            getRows={() =>
              points.map((p) => ({
                month: p.month.slice(0, 7),
                assigned: Number(p.budget_assigned),
                spent: Number(p.actual_spent),
                monthly_variance: Number(p.monthly_variance),
                cumulative_variance: Number(p.cumulative_variance),
              }))
            }
            captureRef={captureRef}
          />
        </div>
      </div>

      <div ref={captureRef} className="report-capture">
      {latest && (
        <div className="report-metrics">
          <MetricCard
            label="Cumulative Variance"
            value={formatMoney(Number(latest.cumulative_variance))}
            sub={Number(latest.cumulative_variance) > 0 ? 'Under budget overall' : 'Over budget overall'}
          />
          <MetricCard label="Last Month Assigned" value={formatMoney(Number(latest.budget_assigned))} />
          <MetricCard label="Last Month Spent" value={formatMoney(Number(latest.actual_spent))} />
        </div>
      )}

      {chartData.length === 0 ? (
        <div className="reports-empty">No data for this period.</div>
      ) : (
        <ResponsiveContainer width="100%" height={340}>
          <ComposedChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
            <XAxis dataKey="month" tick={{ fontSize: 11 }} />
            <YAxis tickFormatter={(v) => formatMoney(v)} tick={{ fontSize: 11 }} width={90} />
            <Tooltip content={<ChartTooltip showTotal={false} />} offset={16} isAnimationActive={false} />
            <Legend />
            <ReferenceLine y={0} stroke="var(--border-color)" strokeWidth={2} />
            <Bar dataKey="Assigned" fill="#4e79a7" opacity={0.6} radius={[2, 2, 0, 0]} />
            <Bar dataKey="Spent" fill="#e15759" opacity={0.6} radius={[2, 2, 0, 0]} />
            <Line type="monotone" dataKey="Cumulative" stroke="#f28e2b" strokeWidth={2.5} dot={{ r: 3 }} />
          </ComposedChart>
        </ResponsiveContainer>
      )}
      </div>
    </div>
  )
}
