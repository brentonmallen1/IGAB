import { useMemo, useRef, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useIncomeBySourceReport } from '../../../api/reports'
import { useFormatters } from '../../../hooks/useFormatters'
import { useChartHeight } from '../../../hooks/useChartHeight'
import { ReportErrorState } from '../ReportErrorState'
import { ReportRangeSelect } from './rangeSelect'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ChartTooltip } from './ChartTooltip'
import { ChartLegend } from './ChartLegend'
import { useReportMonths } from '../../../stores/reportStore'
import { useMoneyAxis } from '../../../hooks/useMoneyAxis'
import { stackedValueAxis } from '../../../utils/axisScale'
import { incomeSourceCount, incomeSourceRows } from './incomeSourcesView'
import { MIXED_SIGN_STACK } from './mixedSignStack'
import { stackTrends } from './spendingTrends'

interface Props {
  budgetId: string
}

const MAX_SERIES = 8

/** Income per payee per month, with a total line — pairs with the paycheck
 *  planner. Only rows the classifier reads as income count. */
export function IncomeSourcesReport({ budgetId }: Props) {
  const { formatMoney, formatMonthShort } = useFormatters()
  const moneyAxis = useMoneyAxis()
  const chartHeight = useChartHeight(320)
  const months = useReportMonths()
  const captureRef = useRef<HTMLDivElement>(null)
  const { data, isLoading, isError, error, refetch } = useIncomeBySourceReport(budgetId, months)

  const [highlight, setHighlight] = useState<string | null>(null)
  // The stack Spending Trends and Subscriptions draw: the largest sources by
  // total, bottom first, and one Other band holding the rest so every bar is
  // its month's income. This chart built its own copy of that stack, keyed by
  // payee NAME — two payees who share a name drew as one — and let recharts
  // write the legend, which sorted it alphabetically rather than in the order
  // the bars stack.
  const stacked = useMemo(
    () =>
      data
        ? stackTrends(data, incomeSourceRows(data.sources), formatMonthShort, MAX_SERIES)
        : { rows: [], series: [] },
    [data, formatMonthShort]
  )
  const axis = useMemo(
    () =>
      stackedValueAxis(
        stacked.rows,
        stacked.series.map((s) => s.key)
      ),
    [stacked]
  )

  if (isLoading) return <div className="report-loading">Loading...</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />
  if (!data) return null

  // Served. This divided by `months.length` with the running month in the
  // window, reading 5,500 beside Cost of Living's Take-home of 6,000 for the
  // same steady pay.
  const avg = data.avg_monthly

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Income by Source</h2>
        <ReportInfoButton title="Income by Source">
          <p>
            Income per payee, month by month. Only rows IGAB reads as income count — transfers
            between your accounts, refunds into an envelope and investment growth are not income.
          </p>
          <p>
            The largest {MAX_SERIES} sources are drawn on their own, bottom first in the order the
            key lists them; the rest share one Other band, so every bar is its month&apos;s income.
            A source can dip below zero — a clawed-back paycheck, an adjustment filed as income.
          </p>
          <ReportScopeNote report="income-sources" />
        </ReportInfoButton>
        <div className="flex-row">
          <ReportRangeSelect />
        </div>
        <div style={{ marginLeft: 'auto' }}>
          <ReportExportButton
            reportId="income-sources"
            getRows={() =>
              data.sources.map((s) => ({
                payee: s.payee_name,
                ...Object.fromEntries(data.months.map((m, i) => [m, s.monthly[i]])),
                total: s.total,
                count: s.count,
              }))
            }
            captureRef={captureRef}
          />
        </div>
      </div>

      {data.sources.length === 0 ? (
        <div className="reports-empty">
          <p>No income in the last {months} months.</p>
        </div>
      ) : (
        <div ref={captureRef} className="report-capture">
          <MetricRow>
            <MetricCard label="Total income" value={formatMoney(data.total)} />
            <MetricCard label="Average / month" value={formatMoney(avg)} />
            <MetricCard label="Sources" value={String(incomeSourceCount(data.sources))} />
          </MetricRow>
          <div className="report-chart" style={{ height: chartHeight }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={stacked.rows}
                margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
                // A payee's month can be negative — a reconciliation
                // adjustment filed to Ready to Assign is income by class.
                {...MIXED_SIGN_STACK}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                <XAxis dataKey="month" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
                <YAxis
                  {...moneyAxis}
                  // Sized to the stacks, a small dip below zero given a
                  // sliver: recharts' own axis spent a whole step on a −$75
                  // adjustment, a quarter of the plot below zero.
                  domain={axis.domain}
                  ticks={axis.ticks}
                  allowDataOverflow
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
                {stacked.series.map((s) => (
                  <Bar
                    key={s.key}
                    dataKey={s.key}
                    name={s.name}
                    stackId="stack"
                    fill={s.color}
                    fillOpacity={highlight && highlight !== s.name ? 0.25 : 1}
                    isAnimationActive={false}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
          <ChartLegend
            series={stacked.series.map((s) => ({
              name: s.name,
              color: s.color,
              value: formatMoney(s.total),
            }))}
            active={highlight}
            onHover={setHighlight}
          />
          <table className="report-table">
            <caption className="sr-only">Income by payee and month</caption>
            <thead>
              <tr>
                <th scope="col" style={{ textAlign: 'left' }}>
                  Source
                </th>
                {data.months.map((m) => (
                  <th key={m} scope="col" style={{ textAlign: 'right' }}>
                    {formatMonthShort(m)}
                  </th>
                ))}
                <th scope="col" style={{ textAlign: 'right' }}>
                  Total
                </th>
              </tr>
            </thead>
            <tbody>
              {data.sources.map((s) => (
                <tr key={s.payee_id ?? '__none__'}>
                  <td>{s.payee_name}</td>
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
