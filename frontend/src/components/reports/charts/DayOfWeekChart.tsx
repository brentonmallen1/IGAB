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
import { CHART_COLORS } from './chartColors'
import { ReportInfoButton, ReportScopeNote, SpendingClassNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ReportNotes } from '../ReportNotes'
import { useReportScope } from '../../../stores/reportStore'
import { drillScope } from '../drillScope'
import { PAYDAY_WINDOW_OPTIONS } from './reportControls'
import { busiestAndQuietest, paydayBars, paydayPeak, shortDay } from './dayPatternsView'

interface Props {
  budgetId: string
}

export function DayPatternsReport({ budgetId }: Props) {
  const chartHeight = useChartHeight(320)
  const { formatMoney, formatMoneyOrDash, formatDate } = useFormatters()
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

  const [paydayWindow, setPaydayWindow] = useState<(typeof PAYDAY_WINDOW_OPTIONS)[number]>(14)
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
  // a flat week captioned "Busiest day — Sunday, $0.00".
  const extremes = busiestAndQuietest(days)

  const chartData = days.map((d) => ({
    name: shortDay(d.day_name),
    fullName: d.day_name,
    dayOfWeek: d.day_of_week,
    // A typical such day, served: the weekday's total over every one of it
    // in the window. The bars were window totals, so a range holding five
    // Saturdays and four Sundays drew Saturday a fifth taller for spending
    // the same.
    avg: d.avg_per_day ?? 0,
    total: d.total,
    weekdays: d.weekdays,
    purchases: d.count,
  }))

  function drillTo(dayOfWeek: number, dayName: string) {
    setDrillDown({
      kind: 'day-of-week',
      label: `${dayName}s`,
      scope: 'leaf',
      dayOfWeek,
      // The classes the bar counted, whichever way each row went: the bar is
      // net of refunds, and an outflow-only list totalled more than it.
      activityClasses: data?.counted_classes,
      ...drillScope(reportScope),
      startDate: filters.startDate,
      endDate: filters.endDate,
    })
  }

  const paydayBaseline = paydayData?.baseline_daily ?? null
  const paydayEventCount = paydayData?.event_count ?? 0
  const paydayFloor = paydayData?.payday_floor
  const paydayChartData = paydayBars(paydayData?.days ?? [], paydayBaseline)
  const peak = paydayPeak(paydayData?.days ?? [])

  return (
    <>
      <div className="report-section surface">
        <div className="report-section__header">
          <h2 className="report-section__title">Day-of-Week Spending Patterns</h2>
          <ReportInfoButton title="Day-of-Week Patterns">
            <p>
              Each bar is an <strong>average</strong> such day: that weekday&apos;s spending over
              the period divided by how many of it the period held, the quiet ones included. The
              busiest is drawn in a second colour. Hover a bar for its total.
            </p>
            <p>
              Days are the bank&apos;s <strong>posting date</strong>, which can trail the purchase —
              a Saturday shop may post on Monday — so weekends can read lighter than they were.
            </p>
            <p>Click a bar to see that weekday&apos;s transactions.</p>
            <ReportScopeNote report="day-patterns" />
            <SpendingClassNote />
          </ReportInfoButton>
          <div className="ms-auto">
            <ReportExportButton
              reportId="day-patterns"
              getRows={() =>
                days.map((d) => ({
                  day: d.day_name,
                  avg_per_day: d.avg_per_day,
                  total: d.total,
                  days_in_range: d.weekdays,
                  purchases: d.count,
                }))
              }
              captureRef={captureRef}
              window={{ start: filters.startDate, end: filters.endDate }}
            />
          </div>
        </div>
        <p className="report-section__subtitle">
          An average day of each weekday, by the bank&apos;s posting date.
          {data && ` ${formatDate(data.window_start)} – ${formatDate(data.window_end)}`}
        </p>

        <div ref={captureRef} className="report-capture">
          {extremes && (
            <MetricRow>
              <MetricCard
                label="Busiest day"
                value={extremes.busiest.day_name}
                sub={`${formatMoneyOrDash(extremes.busiest.avg_per_day)} on an average ${extremes.busiest.day_name}`}
              />
              <MetricCard
                label="Quietest day"
                value={extremes.quietest.day_name}
                sub={`${formatMoneyOrDash(extremes.quietest.avg_per_day)} on an average ${extremes.quietest.day_name}`}
              />
            </MetricRow>
          )}

          {/* Before the empty state, not after: when the selection is all savings
            or debt the week is genuinely blank, and the note is the answer to
            why rather than a footnote under a chart that never drew. */}
          <ReportNotes report={data} toggleAvailable={false} />

          {!extremes ? (
            <div className="reports-empty">No spending data for this period.</div>
          ) : (
            <ResponsiveContainer width="100%" height={chartHeight}>
              <BarChart data={chartData} margin={{ top: 8, right: 20, left: 0, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                <XAxis
                  dataKey="name"
                  interval={0}
                  tick={{ fontSize: 12, fill: 'var(--text-muted)' }}
                />
                <YAxis
                  tickFormatter={moneyAxis.tickFormatter}
                  tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                  width={moneyAxis.width}
                />
                <Tooltip
                  content={({ active, payload }) => {
                    const row = payload?.[0]?.payload as (typeof chartData)[number] | undefined
                    if (!active || !row) return null
                    return (
                      <div className="chart-tooltip">
                        <div className="chart-tooltip__label">{row.fullName}</div>
                        <div className="chart-tooltip__row">
                          <span className="chart-tooltip__name">An average one</span>
                          <span className="chart-tooltip__value">{formatMoney(row.avg)}</span>
                        </div>
                        <div className="chart-tooltip__row">
                          <span className="chart-tooltip__name">
                            All {row.weekdays} in the range
                          </span>
                          <span className="chart-tooltip__value">{formatMoney(row.total)}</span>
                        </div>
                        <div className="chart-tooltip__row">
                          <span className="chart-tooltip__name">Purchases</span>
                          <span className="chart-tooltip__value">{row.purchases}</span>
                        </div>
                      </div>
                    )
                  }}
                  offset={16}
                  isAnimationActive={false}
                />
                <Bar
                  dataKey="avg"
                  radius={[3, 3, 0, 0]}
                  maxBarSize={44}
                  cursor="pointer"
                  onClick={(bar) => {
                    const d = bar as {
                      dayOfWeek?: number
                      fullName?: string
                      payload?: { dayOfWeek?: number; fullName?: string }
                    }
                    const dow = d.dayOfWeek ?? d.payload?.dayOfWeek
                    const name = d.fullName ?? d.payload?.fullName
                    if (dow != null && name) drillTo(dow, name)
                  }}
                >
                  {chartData.map((entry) => (
                    <Cell
                      key={entry.dayOfWeek}
                      fill={
                        entry.dayOfWeek === extremes.busiest.day_of_week
                          ? CHART_COLORS[1]
                          : CHART_COLORS[0]
                      }
                      fillOpacity={0.85}
                    />
                  ))}
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
              Compares your <strong>discretionary spending in the days after each payday</strong>{' '}
              with a typical day.
            </p>
            <p>
              A <strong>payday</strong> is an income deposit — categorized as income, or not yet
              categorized — of {paydayFloor == null ? 'a minimum amount' : formatMoney(paydayFloor)}{' '}
              or more into a cash account. Money moved in from another of your accounts, a credit on
              a credit card, and a refund filed to a spending category are not paydays.
            </p>
            <p>
              Each bar is the <strong>median</strong> payday&apos;s spending that many days after
              it: half your paydays spent more that day, half less, and a payday with nothing spent
              counts as zero. One big purchase after one payday does not move it. The dashed line is
              the median day across the whole period, paydays included.
            </p>
            <p>
              <strong>Discretionary only.</strong> Spending in categories tagged Essential or Cost
              of living, and subscriptions, is left out: bills land on their own dates whatever you
              do after being paid, and counting them would chart your billing calendar. Net of
              refunds, and spending with no category counts as discretionary until you file it.
            </p>
            <ReportScopeNote report="payday-effect" />
          </ReportInfoButton>
          <div
            className="report-section__controls"
            style={{ gap: 4, marginLeft: 'var(--spacing-md)' }}
          >
            {PAYDAY_WINDOW_OPTIONS.map((w) => (
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
          Do you spend more right after getting paid?
          {paydayData &&
            ` ${paydayEventCount} payday${paydayEventCount === 1 ? '' : 's'}, ${formatDate(paydayData.window_start)} – ${formatDate(paydayData.window_end)}.`}
        </p>

        {paydayLoading ? (
          <div className="report-loading">Loading…</div>
        ) : paydayEventCount === 0 ? (
          <div className="reports-empty">No paydays found to compare against.</div>
        ) : (
          <>
            <MetricRow>
              <MetricCard
                label="Typical day"
                value={formatMoneyOrDash(paydayBaseline)}
                sub={`Median of ${paydayData?.baseline_days ?? 0} days`}
              />
              {peak && (
                <MetricCard
                  label="Peak day after payday"
                  value={peak.offset === 0 ? 'Payday' : `Day +${peak.offset}`}
                  sub={`${formatMoney(peak.median_spend)} on the median payday`}
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
                {/* Unlabelled on the plot: its label sat on the bars it
                    crossed. The key below names it. */}
                {paydayBaseline !== null && (
                  <ReferenceLine
                    y={paydayBaseline}
                    stroke="var(--text-muted)"
                    strokeDasharray="4 4"
                  />
                )}
                <Tooltip
                  content={({ active, payload }) => {
                    const row = payload?.[0]?.payload as
                      (typeof paydayChartData)[number] | undefined
                    if (!active || !row) return null
                    return (
                      <div className="chart-tooltip">
                        <div className="chart-tooltip__label">
                          {row.offset === 0 ? 'Payday' : `${row.offset} days after`}
                        </div>
                        <div className="chart-tooltip__row">
                          <span className="chart-tooltip__name">Median payday</span>
                          <span className="chart-tooltip__value">{formatMoney(row.spend)}</span>
                        </div>
                        <div className="chart-tooltip__row">
                          <span className="chart-tooltip__name">Paydays</span>
                          <span className="chart-tooltip__value">{row.paydays}</span>
                        </div>
                      </div>
                    )
                  }}
                  offset={16}
                  isAnimationActive={false}
                />
                <Bar dataKey="spend" radius={[3, 3, 0, 0]} maxBarSize={28}>
                  {paydayChartData.map((entry) => (
                    <Cell
                      key={entry.offset}
                      fill={entry.aboveBaseline ? CHART_COLORS[1] : CHART_COLORS[0]}
                      fillOpacity={0.85}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <div className="chart-key">
              <span className="chart-key__item">
                <span className="chart-key__swatch" style={{ background: CHART_COLORS[1] }} />
                Above a typical day
              </span>
              <span className="chart-key__item">
                <span className="chart-key__swatch" style={{ background: CHART_COLORS[0] }} />
                At or below
              </span>
              {paydayBaseline !== null && (
                <span className="chart-key__item">
                  <span
                    className="chart-key__swatch chart-key__swatch--line"
                    style={{ background: 'var(--text-muted)' }}
                  />
                  Typical day (median)
                </span>
              )}
            </div>
          </>
        )}
      </div>
    </>
  )
}
