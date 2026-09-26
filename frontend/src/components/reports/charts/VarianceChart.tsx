import { useRef } from 'react'
import {
  Bar,
  Cell,
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
import { useMoneyAxis } from '../../../hooks/useMoneyAxis'
import { ReportErrorState } from '../ReportErrorState'
import { ChartTooltip } from './ChartTooltip'
import { CHART_COLORS, COLOR_NEGATIVE, COLOR_NEUTRAL } from './chartColors'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ReportRangeSelect } from './rangeSelect'
import { useReportMonths } from '../../../stores/reportStore'
import {
  completeMonthRows,
  reportMonthLabel,
  RUNNING_MONTH_OPACITY,
  throughMonth,
} from '../../../utils/reportMonths'

interface Props {
  budgetId: string
}

export function VarianceReport({ budgetId }: Props) {
  const chartHeight = useChartHeight(340)
  const { formatMoney, formatMonthShort } = useFormatters()
  const moneyAxis = useMoneyAxis()
  const months = useReportMonths()
  const { data, isLoading, isError, error, refetch } = useVarianceReport(budgetId, months)
  const captureRef = useRef<HTMLDivElement>(null)

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  const points = data?.points ?? []
  // The drift is the complete months'; the running month's own figures so
  // far sit beside it on their own cards.
  const settled = completeMonthRows(points).at(-1)
  const running = points.find((p) => p.partial_month)

  const chartData = points.map((p) => ({
    iso: p.month,
    month: reportMonthLabel(p.month, p.partial_month, formatMonthShort),
    partial: p.partial_month,
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
          <p>
            The drift covers complete months only. The month in progress is drawn after them,
            lighter and marked <em>so far</em>, with no point on the line: its whole plan is in from
            the 1st while its spending arrives over the month.
          </p>
          <ReportScopeNote report="variance" />
        </ReportInfoButton>
        <p className="report-section__subtitle">Running budget drift over time</p>
        <div className="flex-row ms-auto">
          <ReportRangeSelect />
          <ReportExportButton
            reportId="variance"
            getRows={() =>
              points.map((p) => ({
                month: p.month.slice(0, 7),
                partial_month: p.partial_month,
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
        {(settled || running) && (
          <MetricRow>
            {settled && settled.cumulative_variance !== null && (
              <MetricCard
                label="Cumulative Variance"
                value={formatMoney(settled.cumulative_variance)}
                sub={`${
                  settled.cumulative_variance > 0 ? 'Under budget' : 'Over budget'
                } ${throughMonth(settled.month, formatMonthShort)}`}
              />
            )}
            {/* The running month (`ReportWindow`), apart from the drift:
                "Last Month Spent" once read a half-finished month as whole. */}
            {running && (
              <>
                <MetricCard
                  label="Assigned this month so far"
                  value={formatMoney(running.budget_assigned)}
                />
                <MetricCard
                  label="Spent this month so far"
                  value={formatMoney(running.actual_spent)}
                />
              </>
            )}
          </MetricRow>
        )}

        {chartData.length === 0 ? (
          <div className="reports-empty">No data for this period.</div>
        ) : (
          <ResponsiveContainer width="100%" height={chartHeight}>
            <ComposedChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
              <XAxis dataKey="month" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
              <YAxis {...moneyAxis} tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
              <Tooltip
                content={<ChartTooltip showTotal={false} formatter={formatMoney} />}
                offset={16}
                isAnimationActive={false}
              />
              <Legend />
              <ReferenceLine y={0} stroke="var(--border-color)" strokeWidth={2} />
              <Bar dataKey="Assigned" fill={COLOR_NEUTRAL} opacity={0.6} radius={[2, 2, 0, 0]}>
                {chartData.map((d) => (
                  <Cell key={d.iso} fillOpacity={d.partial ? RUNNING_MONTH_OPACITY : 1} />
                ))}
              </Bar>
              <Bar dataKey="Spent" fill={COLOR_NEGATIVE} opacity={0.6} radius={[2, 2, 0, 0]}>
                {chartData.map((d) => (
                  <Cell key={d.iso} fillOpacity={d.partial ? RUNNING_MONTH_OPACITY : 1} />
                ))}
              </Bar>
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
