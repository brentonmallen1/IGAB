import { useRef, useState } from 'react'
import {
  Bar,
  ComposedChart,
  CartesianGrid,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useVarianceReport } from '../../../api/reports'
import { useChartHeight } from '../../../hooks/useChartHeight'
import { useFormatters } from '../../../hooks/useFormatters'
import { ReportErrorState } from '../ReportErrorState'
import { ChartTooltip } from './ChartTooltip'
import { CHART_COLORS, COLOR_NEGATIVE, COLOR_NEUTRAL } from './chartColors'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ReportRangeButtons } from './rangeButtons'

interface Props {
  budgetId: string
}

export function VarianceReport({ budgetId }: Props) {
  const chartHeight = useChartHeight(340)
  const { formatMoney } = useFormatters()
  const [months, setMonths] = useState(12)
  const { data, isLoading, isError, error, refetch } = useVarianceReport(budgetId, months)
  const captureRef = useRef<HTMLDivElement>(null)

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  const points = data?.points ?? []
  const latest = points[points.length - 1]

  const chartData = points.map((p) => ({
    month: p.month.slice(0, 7),
    Assigned: p.budget_assigned,
    Spent: p.actual_spent,
    'Monthly Variance': p.monthly_variance,
    Cumulative: p.cumulative_variance,
  }))

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Cumulative Budget Variance</h2>
        <ReportInfoButton title="Cumulative Budget Variance">
          <p>
            Tracks the <strong>running total of assigned minus spent</strong> across all months.
            Positive = you've been consistently under budget; negative = you've been consistently
            over.
          </p>
          <p>
            The <strong>bars</strong> show the monthly assigned vs spent gap. The{' '}
            <strong>line</strong> is the cumulative drift — if it slopes down, your budget is
            eroding month by month.
          </p>
          <ReportScopeNote scope="categories" />
        </ReportInfoButton>
        <p className="report-section__subtitle">Running budget drift over time</p>
        <div className="flex-row ms-auto">
          <ReportRangeButtons months={months} onChange={setMonths} />
          <ReportExportButton
            reportId="variance"
            getRows={() =>
              points.map((p) => ({
                month: p.month.slice(0, 7),
                assigned: p.budget_assigned,
                spent: p.actual_spent,
                monthly_variance: p.monthly_variance,
                cumulative_variance: p.cumulative_variance,
              }))
            }
            captureRef={captureRef}
          />
        </div>
      </div>

      <div ref={captureRef} className="report-capture">
        {latest && (
          <MetricRow>
            <MetricCard
              label="Cumulative Variance"
              value={formatMoney(latest.cumulative_variance)}
              sub={latest.cumulative_variance > 0 ? 'Under budget overall' : 'Over budget overall'}
            />
            <MetricCard label="Last Month Assigned" value={formatMoney(latest.budget_assigned)} />
            <MetricCard label="Last Month Spent" value={formatMoney(latest.actual_spent)} />
          </MetricRow>
        )}

        {chartData.length === 0 ? (
          <div className="reports-empty">No data for this period.</div>
        ) : (
          <ResponsiveContainer width="100%" height={chartHeight}>
            <ComposedChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
              <XAxis dataKey="month" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
              <YAxis
                tickFormatter={(v) => formatMoney(v)}
                tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                width={90}
              />
              <Tooltip
                content={<ChartTooltip showTotal={false} />}
                offset={16}
                isAnimationActive={false}
              />
              <Legend />
              <ReferenceLine y={0} stroke="var(--border-color)" strokeWidth={2} />
              <Bar dataKey="Assigned" fill={COLOR_NEUTRAL} opacity={0.6} radius={[2, 2, 0, 0]} />
              <Bar dataKey="Spent" fill={COLOR_NEGATIVE} opacity={0.6} radius={[2, 2, 0, 0]} />
              <Line
                type="monotone"
                dataKey="Cumulative"
                stroke={CHART_COLORS[1]}
                strokeWidth={2.5}
                dot={{ r: 3 }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
