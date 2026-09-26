import { useRef } from 'react'
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
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
import { ChartLegend } from './ChartLegend'
import { COLOR_NEGATIVE, COLOR_NET, COLOR_NEUTRAL, COLOR_POSITIVE } from './chartColors'
import { varianceBarColor, varianceTooltipRows } from './varianceView'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ReportRangeSelect } from './rangeSelect'
import { useReportMonths } from '../../../stores/reportStore'
import type { VariancePoint } from '../../../types'
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
    month: reportMonthLabel(p.month, p.partial_month, formatMonthShort),
    'This month': p.monthly_variance,
    'Running total': p.cumulative_variance,
    point: p,
  }))

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Cumulative Budget Variance</h2>
        <ReportInfoButton title="Cumulative Budget Variance">
          <p>
            Each <strong>bar</strong> is one month&apos;s plan minus what it spent: green under
            plan, red over. A month&apos;s plan is what you assigned plus money moved into
            envelopes, less money moved out of them, and spending is net of refunds.
          </p>
          <p>
            The <strong>line</strong> is the running total of those bars. Above zero you have spent
            less than planned overall; below it, more. If it slopes down, the plan is eroding month
            by month. Hover a month for its plan and spending.
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
                moved_in: p.moved_in,
                moved_out: p.moved_out,
                planned: p.planned,
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
                  label="Planned this month so far"
                  value={formatMoney(running.planned)}
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
            {/* One axis, one zero: the bars and the line are the same kind of
                figure (plan minus spent), so they share it. */}
            <ComposedChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
              <XAxis dataKey="month" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
              <YAxis {...moneyAxis} tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
              <Tooltip
                content={({ active, payload, label }) => {
                  const row = payload?.[0]?.payload as { point?: VariancePoint } | undefined
                  return (
                    <ChartTooltip
                      active={active}
                      payload={row?.point ? varianceTooltipRows(row.point) : []}
                      label={String(label ?? '')}
                      formatter={formatMoney}
                    />
                  )
                }}
                offset={16}
                isAnimationActive={false}
              />
              <ReferenceLine y={0} stroke="var(--border-color)" strokeWidth={2} />
              <Bar dataKey="This month" fill={COLOR_NEUTRAL} radius={[2, 2, 0, 0]}>
                {points.map((p) => (
                  <Cell
                    key={p.month}
                    fill={varianceBarColor(p.monthly_variance)}
                    fillOpacity={p.partial_month ? RUNNING_MONTH_OPACITY : 1}
                  />
                ))}
              </Bar>
              <Line
                type="linear"
                dataKey="Running total"
                stroke={COLOR_NET}
                strokeWidth={2.5}
                dot={{ r: 3 }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        )}
        {chartData.length > 0 && (
          // Recharts' own legend keys a series by its fill, and the bars take
          // their colour from their month's state — so it drew one swatch in
          // a colour no bar had.
          <ChartLegend
            series={[
              { name: 'Month under plan', color: COLOR_POSITIVE },
              { name: 'Month over plan', color: COLOR_NEGATIVE },
              { name: 'Running total', color: COLOR_NET },
            ]}
            active={null}
            onHover={() => {}}
          />
        )}
      </div>
    </div>
  )
}
