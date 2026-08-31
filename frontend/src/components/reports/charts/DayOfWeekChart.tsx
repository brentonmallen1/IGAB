import { useRef, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Cell,
} from 'recharts'
import { useReportStore } from '../../../stores/reportStore'
import { useDayPatternsReport, usePaydayEffectReport } from '../../../api/reports'
import { useChartHeight } from '../../../hooks/useChartHeight'
import { useFormatters } from '../../../hooks/useFormatters'
import { ReportErrorState } from '../ReportErrorState'
import { MetricCard } from '../MetricCard'
import { CHART_COLORS, TOOLTIP_STYLE } from './chartColors'
import { ReportInfoButton, ReportScopeNote, SpendingClassNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ReportNotes } from '../ReportNotes'

interface Props {
  budgetId: string
}

const WINDOW_OPTIONS = [7, 14, 21] as const

export function DayPatternsReport({ budgetId }: Props) {
  const chartHeight = useChartHeight(320)
  const { formatMoney } = useFormatters()
  const { filters, setDrillDown } = useReportStore()
  const catIds = filters.categoryIds.length > 0 ? filters.categoryIds : undefined
  const acctIds = filters.accountIds.length > 0 ? filters.accountIds : undefined
  const { data, isLoading, isError, error, refetch } = useDayPatternsReport(
    budgetId,
    filters.startDate,
    filters.endDate,
    catIds,
    acctIds
  )
  const captureRef = useRef<HTMLDivElement>(null)

  const [paydayWindow, setPaydayWindow] = useState<(typeof WINDOW_OPTIONS)[number]>(14)
  const { data: paydayData, isLoading: paydayLoading } = usePaydayEffectReport(
    budgetId,
    paydayWindow,
    12
  )

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  const days = data?.days ?? []
  // The API always returns seven rows, zeroed when nothing matched — so
  // `days.length` never reports emptiness. Filter to a category whose activity
  // is all debt principal and this is the difference between "no spending" and
  // a flat week captioned "Highest Spending Day — Sunday, $0.00".
  const hasSpending = days.some((d) => Number(d.total) > 0)

  const maxDay = days.reduce(
    (best, d) => (Number(d.total) > Number(best.total) ? d : best),
    days[0]
  )
  const minDay = days.reduce(
    (least, d) => (Number(d.total) < Number(least.total) ? d : least),
    days[0]
  )

  const chartData = days.map((d) => ({
    name: d.day_name,
    dayOfWeek: d.day_of_week,
    Amount: Number(d.total),
    Transactions: d.count,
    avgPerTxn: d.count > 0 ? Number(d.total) / d.count : 0,
  }))

  function drillTo(dayOfWeek: number, dayName: string) {
    setDrillDown({
      kind: 'day-of-week',
      label: `${dayName}s`,
      scope: 'leaf',
      direction: 'outflow',
      dayOfWeek,
      categoryIds: filters.categoryIds.length > 0 ? filters.categoryIds : undefined,
      startDate: filters.startDate,
      endDate: filters.endDate,
    })
  }

  const paydayDays = paydayData?.days ?? []
  const paydayBaseline = Number(paydayData?.baseline_daily ?? 0)
  const paydayEventCount = paydayData?.event_count ?? 0

  const paydayChartData = paydayDays.map((d) => ({
    name: d.offset === 0 ? 'Payday' : `+${d.offset}`,
    offset: d.offset,
    spend: Number(d.avg_spend),
    aboveBaseline: Number(d.avg_spend) > paydayBaseline,
  }))

  const paydayPeakDay = paydayDays.reduce(
    (best, d) => (Number(d.avg_spend) > Number(best.avg_spend) ? d : best),
    paydayDays[0]
  )

  return (
    <>
      <div className="report-section surface">
        <div className="report-section__header">
          <h2 className="report-section__title">Day-of-Week Spending Patterns</h2>
          <ReportInfoButton title="Day-of-Week Patterns">
            <p>
              Total spending aggregated by day of week across all transactions in the selected
              period. The <strong>peak day is highlighted</strong> in a different color.
            </p>
            <p>
              High weekday spending often signals structured habits (groceries, work lunches). High
              weekend spending can indicate impulse or leisure spending. Use this to identify which
              days need more discipline.
            </p>
            <p>Click a bar to see that weekday's transactions.</p>
            <ReportScopeNote scope="on-budget-filterable" />
            <SpendingClassNote />
          </ReportInfoButton>
          <div className="ms-auto">
            <ReportExportButton
              reportId="day-patterns"
              getRows={() =>
                days.map((d) => ({
                  day: d.day_name,
                  total: Number(d.total),
                  count: d.count,
                  avg_transaction: d.count > 0 ? Number(d.total) / d.count : 0,
                }))
              }
              captureRef={captureRef}
              window={{ start: filters.startDate, end: filters.endDate }}
            />
          </div>
        </div>
        <p className="report-section__subtitle">
          When do you spend the most? Reveals impulse vs structured spending habits.
        </p>

        <div ref={captureRef} className="report-capture">
          {hasSpending && maxDay && minDay && (
            <div className="report-metrics">
              <MetricCard
                label="Highest Spending Day"
                value={maxDay.day_name}
                sub={formatMoney(Number(maxDay.total))}
              />
              <MetricCard
                label="Lowest Spending Day"
                value={minDay.day_name}
                sub={formatMoney(Number(minDay.total))}
              />
            </div>
          )}

          {/* Before the empty state, not after: when the selection is all savings
            or debt the week is genuinely blank, and the note is the answer to
            why rather than a footnote under a chart that never drew. */}
          <ReportNotes report={data} toggleAvailable={false} />

          {!hasSpending ? (
            <div className="reports-empty">No spending data for this period.</div>
          ) : (
            <ResponsiveContainer width="100%" height={chartHeight}>
              <BarChart data={chartData} margin={{ top: 8, right: 20, left: 0, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                <XAxis dataKey="name" tick={{ fontSize: 12, fill: 'var(--text-muted)' }} />
                <YAxis
                  tickFormatter={(v) => formatMoney(v)}
                  tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                  width={80}
                />
                <Tooltip
                  formatter={(v: unknown, name: unknown) =>
                    name === 'Amount' ? [formatMoney(Number(v)), name] : [Number(v), String(name)]
                  }
                  offset={16}
                  isAnimationActive={false}
                  {...TOOLTIP_STYLE}
                />
                <Bar
                  dataKey="Amount"
                  radius={[3, 3, 0, 0]}
                  barSize={44}
                  cursor="pointer"
                  onClick={(data) => {
                    const d = data as {
                      dayOfWeek?: number
                      name?: string
                      payload?: { dayOfWeek?: number; name?: string }
                    }
                    const dow = d.dayOfWeek ?? d.payload?.dayOfWeek
                    const name = d.name ?? d.payload?.name
                    if (dow != null && name) drillTo(dow, name)
                  }}
                >
                  {chartData.map((entry, i) => {
                    const isMax = maxDay && entry.name === maxDay.day_name
                    return (
                      <Cell
                        key={i}
                        fill={isMax ? CHART_COLORS[1] : CHART_COLORS[0]}
                        fillOpacity={0.85}
                      />
                    )
                  })}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      <div className="report-section surface" style={{ marginTop: 'var(--spacing-lg)' }}>
        <div className="report-section__controls">
          <h2 className="report-section__title">Payday Effect</h2>
          <ReportInfoButton title="Payday Effect">
            <p>
              Analyzes your <strong>spending behavior after large income deposits</strong>{' '}
              (paychecks, bonuses, etc.). Compares daily spending in the days following income
              events against your baseline daily spending.
            </p>
            <p>
              Bars above the dashed baseline indicate higher-than-normal spending. Many people spend
              more right after payday — this visualization helps you see if that pattern applies to
              you.
            </p>
            <p>
              <strong>Note:</strong> Subscriptions and scheduled bills are excluded to isolate
              discretionary spending patterns.
            </p>
            <ReportScopeNote scope="on-budget" />
          </ReportInfoButton>
          <div
            className="report-section__controls"
            style={{ gap: 4, marginLeft: 'var(--spacing-md)' }}
          >
            {WINDOW_OPTIONS.map((w) => (
              <button
                key={w}
                className={`report-btn ${paydayWindow === w ? 'report-btn--active' : ''}`}
                onClick={() => setPaydayWindow(w)}
                type="button"
              >
                {w} days
              </button>
            ))}
          </div>
        </div>
        <p className="report-section__subtitle">
          Do you spend more right after getting paid? Based on {paydayEventCount} income events in
          the last 12 months.
        </p>

        {paydayLoading ? (
          <div className="report-loading">Loading…</div>
        ) : paydayEventCount === 0 ? (
          <div className="reports-empty">
            Not enough income events detected to analyze payday spending patterns.
          </div>
        ) : (
          <>
            <div className="report-metrics">
              <MetricCard
                label="Baseline Daily"
                value={formatMoney(paydayBaseline)}
                sub="Average on non-payday periods"
              />
              {paydayPeakDay && (
                <MetricCard
                  label="Peak Spending Day"
                  value={paydayPeakDay.offset === 0 ? 'Payday' : `Day +${paydayPeakDay.offset}`}
                  sub={formatMoney(Number(paydayPeakDay.avg_spend))}
                />
              )}
            </div>

            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={paydayChartData} margin={{ top: 8, right: 20, left: 0, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                <XAxis dataKey="name" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
                <YAxis
                  tickFormatter={(v) => formatMoney(v)}
                  tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                  width={80}
                />
                <ReferenceLine
                  y={paydayBaseline}
                  stroke="var(--text-muted)"
                  strokeDasharray="4 4"
                  label={{
                    value: 'Baseline',
                    position: 'insideTopRight',
                    fill: 'var(--text-muted)',
                    fontSize: 11,
                  }}
                />
                <Tooltip
                  formatter={(v: unknown) => [formatMoney(Number(v)), 'Avg Daily Spend']}
                  offset={16}
                  isAnimationActive={false}
                  {...TOOLTIP_STYLE}
                />
                <Bar dataKey="spend" radius={[3, 3, 0, 0]} barSize={28}>
                  {paydayChartData.map((entry, i) => (
                    <Cell
                      key={i}
                      fill={entry.aboveBaseline ? 'var(--color-warning)' : CHART_COLORS[0]}
                      fillOpacity={0.85}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </>
        )}
      </div>
    </>
  )
}
