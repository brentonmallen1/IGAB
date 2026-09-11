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
import { useMoneyAxis } from '../../../hooks/useMoneyAxis'
import { ReportErrorState } from '../ReportErrorState'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { CHART_COLORS, TOOLTIP_STYLE } from './chartColors'
import { ReportInfoButton, ReportScopeNote, SpendingClassNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ReportNotes } from '../ReportNotes'
import { useReportScope } from '../../../stores/reportStore'
import { drillScope } from '../drillScope'

interface Props {
  budgetId: string
}

const WINDOW_OPTIONS = [7, 14, 21] as const

export function DayPatternsReport({ budgetId }: Props) {
  const chartHeight = useChartHeight(320)
  const { formatMoney, formatMoneyOrDash } = useFormatters()
  const moneyAxis = useMoneyAxis()
  const { filters, setDrillDown } = useReportStore()
  const reportScope = useReportScope()
  const acctIds = filters.accountIds.length > 0 ? filters.accountIds : undefined
  const { data, isLoading, isError, error, refetch } = useDayPatternsReport(
    budgetId,
    filters.startDate,
    filters.endDate,
    reportScope,
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
  const hasSpending = days.some((d) => d.total > 0)

  const maxDay = days.reduce((best, d) => (d.total > best.total ? d : best), days[0])
  const minDay = days.reduce((least, d) => (d.total < least.total ? d : least), days[0])

  const chartData = days.map((d) => ({
    name: d.day_name,
    dayOfWeek: d.day_of_week,
    Amount: d.total,
    Transactions: d.count,
    // The served figure. This was re-derived here and again in the
    // export, so three places computed one number and the server's went
    // unread.
    avgPerTxn: d.avg_transaction,
  }))

  function drillTo(dayOfWeek: number, dayName: string) {
    setDrillDown({
      kind: 'day-of-week',
      label: `${dayName}s`,
      scope: 'leaf',
      direction: 'outflow',
      dayOfWeek,
      // The classes the bar counted. Without them the panel filtered to
      // nothing and totalled more than the bar that opened it.
      activityClasses: data?.counted_classes,
      ...drillScope(reportScope),
      startDate: filters.startDate,
      endDate: filters.endDate,
    })
  }

  const paydayDays = paydayData?.days ?? []
  // null means the payday windows cover every day: there is no baseline, and
  // `?? 0` here invented the $0.00 the server refuses to send — the card read
  // "Baseline Daily $0.00" and every bar with any spend turned warning.
  const servedBaseline = paydayData?.baseline_daily
  const paydayBaseline = servedBaseline == null ? null : Number(servedBaseline)
  const paydayEventCount = paydayData?.event_count ?? 0
  const paydayFloor = paydayData?.payday_floor

  const paydayChartData = paydayDays.map((d) => ({
    name: d.offset === 0 ? 'Payday' : `+${d.offset}`,
    offset: d.offset,
    spend: d.avg_spend,
    aboveBaseline: paydayBaseline !== null && d.avg_spend > paydayBaseline,
  }))

  const paydayPeakDay = paydayDays.reduce(
    (best, d) => (d.avg_spend > best.avg_spend ? d : best),
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
                  total: d.total,
                  count: d.count,
                  avg_transaction: d.avg_transaction,
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
            <MetricRow>
              <MetricCard
                label="Highest Spending Day"
                value={maxDay.day_name}
                sub={formatMoney(maxDay.total)}
              />
              <MetricCard
                label="Lowest Spending Day"
                value={minDay.day_name}
                sub={formatMoney(minDay.total)}
              />
            </MetricRow>
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
                  tickFormatter={moneyAxis.tickFormatter}
                  tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                  width={moneyAxis.width}
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
              Compares your <strong>spending in the days after each payday</strong> with your
              baseline daily spending.
            </p>
            <p>
              A <strong>payday</strong> is an income deposit — categorized as income, or not yet
              categorized — of {paydayFloor == null ? 'a minimum amount' : formatMoney(paydayFloor)}{' '}
              or more into a cash account. Money moved in from another of your accounts, a credit on
              a credit card, and a refund filed to a spending category are not paydays.
            </p>
            <p>
              Each bar is the average spent that many days after a payday, across every payday; a
              payday with nothing spent that day counts as zero. The dashed baseline is your average
              daily spending on the days, from the first payday on, that fall outside every payday
              window. When paydays come often enough to cover every day, there is no baseline.
            </p>
            <p>
              Bars above the baseline indicate higher-than-normal spending. Many people spend more
              right after payday — this shows whether that pattern applies to you.
            </p>
            <p>
              <strong>Note:</strong> Subscriptions are excluded — they land on their own schedule,
              whatever you do after being paid.
            </p>
            <ReportScopeNote scope="on-budget" />
            <SpendingClassNote />
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
            <MetricRow>
              <MetricCard
                label="Baseline Daily"
                value={formatMoneyOrDash(paydayBaseline)}
                sub={
                  paydayBaseline === null
                    ? 'No days fall outside a payday window'
                    : 'Average on non-payday periods'
                }
              />
              {paydayPeakDay && (
                <MetricCard
                  label="Peak Spending Day"
                  value={paydayPeakDay.offset === 0 ? 'Payday' : `Day +${paydayPeakDay.offset}`}
                  sub={formatMoney(paydayPeakDay.avg_spend)}
                />
              )}
            </MetricRow>

            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={paydayChartData} margin={{ top: 8, right: 20, left: 0, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                <XAxis dataKey="name" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
                <YAxis
                  tickFormatter={moneyAxis.tickFormatter}
                  tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                  width={moneyAxis.width}
                />
                {paydayBaseline !== null && (
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
                )}
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
