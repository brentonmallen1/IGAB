import { useMemo, useRef, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useSpendingTrendsReport } from '../../../api/reports'
import { useReportStore, resolveGroupBy } from '../../../stores/reportStore'
import { useFormatters } from '../../../hooks/useFormatters'
import { useChartHeight } from '../../../hooks/useChartHeight'
import { ReportErrorState } from '../ReportErrorState'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { ReportInfoButton, ReportScopeNote, SpendingClassNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ChartTooltip } from './ChartTooltip'
import { ChartLegend } from './ChartLegend'
import { MIXED_SIGN_STACK } from './mixedSignStack'
import { OTHER_KEY, rollupTrends, stackTrends } from './spendingTrends'
import { useReportScope } from '../../../stores/reportStore'
import { useMoneyAxis } from '../../../hooks/useMoneyAxis'
import { ReportNotes, IncludeSavingsToggle } from '../ReportNotes'
import { reportMonthLabel } from '../../../utils/reportMonths'
import { averagedOver } from './averagedOver'

interface Props {
  budgetId: string
}

/**
 * Spending over time for a chosen set of categories — the basic report that
 * was missing. Scope is the shared category filter, plus a saved filter and
 * tags of its own; the server resolves the union, so a saved filter that
 * follows a tag follows it here too.
 */
export function SpendingTrendsReport({ budgetId }: Props) {
  const { formatMoney, formatMoneyOrDash, formatMonthShort } = useFormatters()
  const moneyAxis = useMoneyAxis()
  const chartHeight = useChartHeight(340)
  const { filters } = useReportStore()
  const groupBy = resolveGroupBy('spending-trends', filters.groupBy)
  const [includeSavings, setIncludeSavings] = useState(false)
  const [chart, setChart] = useState<'stacked' | 'lines'>('stacked')
  // Which series the legend is pointing at. The palette repeats past its
  // eighth slot, so this is what tells two same-coloured series apart.
  const [highlight, setHighlight] = useState<string | null>(null)
  const captureRef = useRef<HTMLDivElement>(null)

  const reportScope = useReportScope()
  const { data, isLoading, isError, error, refetch } = useSpendingTrendsReport(
    budgetId,
    filters.startDate,
    filters.endDate,
    reportScope,
    filters.accountIds.length ? filters.accountIds : undefined,
    includeSavings
  )

  const rolled = useMemo(() => (data ? rollupTrends(data, groupBy) : []), [data, groupBy])
  // One label for every month on the page: "Sep 26", and "Sep 26 so far" for
  // the running month, which the server names.
  const runningMonth = data?.running_month ?? null
  const monthLabel = useMemo(
    () => (m: string) => reportMonthLabel(m, m === runningMonth, formatMonthShort),
    [runningMonth, formatMonthShort]
  )
  // Bars stack every named series plus Other, so each is its month's total.
  // Lines draw the named series alone: they are not a stack, and an Other
  // line would be a series nobody asked to follow.
  const stacked = useMemo(
    () => (data ? stackTrends(data, rolled, monthLabel) : { rows: [], series: [] }),
    [data, rolled, monthLabel]
  )
  const series =
    chart === 'stacked' ? stacked.series : stacked.series.filter((s) => s.key !== OTHER_KEY)

  if (isLoading) return <div className="report-loading">Loading...</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />
  if (!data) return null

  // The average is served over the months the range holds whole and that are
  // over: a range through today drew the running month and divided by it.
  const lastMonth = data.months[data.months.length - 1]
  const last = data.monthly_totals[data.monthly_totals.length - 1] ?? 0

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Spending Trends</h2>
        <ReportInfoButton title="Spending Trends">
          <p>
            What was spent, month by month, in the categories you choose. Pick categories in the
            filter bar, a saved filter, or a tag — a saved filter that follows a tag follows it here
            too, because the server works out which categories it means.
          </p>
          <p>
            Savings and debt payments are left out unless you include them; a note says how much
            that was, so a car payment that is missing is never mistaken for lost data.
          </p>
          <p>
            The average counts complete months only; a month still running is shown as &ldquo;so
            far&rdquo; and left out of it.
          </p>
          <ReportScopeNote report="spending-trends" />
          <SpendingClassNote />
        </ReportInfoButton>
        <div className="flex-row">
          <button
            type="button"
            className={`report-btn ${chart === 'stacked' ? 'report-btn--active' : ''}`}
            onClick={() => setChart('stacked')}
          >
            Bars
          </button>
          <button
            type="button"
            className={`report-btn ${chart === 'lines' ? 'report-btn--active' : ''}`}
            onClick={() => setChart('lines')}
          >
            Lines
          </button>
          <IncludeSavingsToggle checked={includeSavings} onChange={setIncludeSavings} />
        </div>
        <div style={{ marginLeft: 'auto' }}>
          <ReportExportButton
            reportId="spending-trends"
            getRows={() =>
              rolled.map((s) => ({
                name: s.name,
                group: s.group_name ?? '',
                ...Object.fromEntries(data.months.map((m, i) => [m, s.monthly[i]])),
                total: s.total,
              }))
            }
            captureRef={captureRef}
          />
        </div>
      </div>

      {/* `ReportNotes`, not a fourth inline copy of the same sentence. This
          chart had its own wording for the class-excluded note and its own
          — inverted — wording for the missing-filter one, which said "showing
          everything" while the server shows nothing. */}
      <ReportNotes report={data} toggleAvailable={!includeSavings} />

      {rolled.length === 0 ? (
        <div className="reports-empty">
          <p>Nothing spent in this scope over the window.</p>
        </div>
      ) : (
        <div ref={captureRef} className="report-capture">
          <MetricRow>
            <MetricCard label="Total" value={formatMoney(data.total)} />
            <MetricCard
              label="Average / month"
              value={formatMoneyOrDash(data.avg_monthly)}
              sub={
                data.months_averaged > 0
                  ? averagedOver('per month', data.months_averaged)
                  : 'no complete month in this range'
              }
            />
            {lastMonth && <MetricCard label={monthLabel(lastMonth)} value={formatMoney(last)} />}
          </MetricRow>

          <div className="report-chart" style={{ height: chartHeight }}>
            <ResponsiveContainer width="100%" height="100%">
              {chart === 'stacked' ? (
                <BarChart
                  data={stacked.rows}
                  {...MIXED_SIGN_STACK}
                  margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                  <XAxis dataKey="month" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
                  <YAxis
                    {...moneyAxis}
                    tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    content={({ active, payload, label }) => (
                      <ChartTooltip
                        active={active}
                        payload={payload?.map((p) => ({
                          name: String(p.name ?? ''),
                          value: Number(p.value ?? 0),
                          color: p.color,
                          fill: p.fill,
                        }))}
                        label={String(label ?? '')}
                        showTotal
                        formatter={formatMoney}
                      />
                    )}
                  />
                  {series.map((s) => (
                    <Bar
                      key={s.key}
                      dataKey={s.key}
                      name={s.name}
                      stackId="stack"
                      fill={s.color}
                      fillOpacity={highlight && highlight !== s.key ? 0.25 : 1}
                      isAnimationActive={false}
                    />
                  ))}
                </BarChart>
              ) : (
                <LineChart data={stacked.rows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                  <XAxis dataKey="month" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
                  <YAxis
                    {...moneyAxis}
                    tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    content={({ active, payload, label }) => (
                      <ChartTooltip
                        active={active}
                        payload={payload?.map((p) => ({
                          name: String(p.name ?? ''),
                          value: Number(p.value ?? 0),
                          color: p.color,
                          fill: p.fill,
                        }))}
                        label={String(label ?? '')}
                        formatter={formatMoney}
                      />
                    )}
                  />
                  {series.map((s) => (
                    <Line
                      key={s.key}
                      type="monotone"
                      dataKey={s.key}
                      name={s.name}
                      stroke={s.color}
                      strokeOpacity={highlight && highlight !== s.key ? 0.2 : 1}
                      dot={false}
                      strokeWidth={2}
                      isAnimationActive={false}
                    />
                  ))}
                </LineChart>
              )}
            </ResponsiveContainer>
          </div>

          {/* In stack order, not recharts' own legend: past eight series the
              palette repeats, and this list is what says which is which. */}
          <ChartLegend
            series={series.map((s) => ({
              id: s.key,
              name: s.name,
              color: s.color,
              value: formatMoney(s.total),
            }))}
            active={highlight}
            onHover={setHighlight}
          />

          <table className="report-table">
            <caption className="sr-only">Spending by month</caption>
            <thead>
              <tr>
                <th scope="col" style={{ textAlign: 'left' }}>
                  {groupBy === 'group' ? 'Group' : 'Category'}
                </th>
                {data.months.map((m) => (
                  <th key={m} scope="col" style={{ textAlign: 'right' }}>
                    {monthLabel(m)}
                  </th>
                ))}
                <th scope="col" style={{ textAlign: 'right' }}>
                  Total
                </th>
              </tr>
            </thead>
            <tbody>
              {rolled.map((s) => (
                <tr key={s.key}>
                  <td>
                    {s.name}
                    {groupBy === 'category' && s.group_name && (
                      <span style={{ color: 'var(--text-muted)' }}> · {s.group_name}</span>
                    )}
                  </td>
                  {s.monthly.map((v, i) => (
                    <td key={i} style={{ textAlign: 'right' }}>
                      {v ? formatMoney(v) : '—'}
                    </td>
                  ))}
                  <td style={{ textAlign: 'right', fontWeight: 600 }}>{formatMoney(s.total)}</td>
                </tr>
              ))}
              <tr>
                <td style={{ fontWeight: 600 }}>All</td>
                {data.monthly_totals.map((v, i) => (
                  <td key={i} style={{ textAlign: 'right', fontWeight: 600 }}>
                    {formatMoney(v)}
                  </td>
                ))}
                <td style={{ textAlign: 'right', fontWeight: 600 }}>{formatMoney(data.total)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
