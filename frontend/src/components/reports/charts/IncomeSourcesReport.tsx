import { useMemo, useRef } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useIncomeBySourceReport } from '../../../api/reports'
import { useFormatters } from '../../../hooks/useFormatters'
import { useChartHeight } from '../../../hooks/useChartHeight'
import { ReportErrorState } from '../ReportErrorState'
import { ReportRangeSelect } from './rangeSelect'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { ReportInfoButton } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ChartTooltip } from './ChartTooltip'
import { chartColor, COLOR_OTHER } from './chartColors'
import { useReportMonths } from '../../../stores/reportStore'
import { useMoneyAxis } from '../../../hooks/useMoneyAxis'
import { incomeSourceCount, otherIncome } from './incomeSourcesView'

interface Props {
  budgetId: string
}

const MAX_SERIES = 8

/** Income per payee per month, with a total line — pairs with the paycheck
 *  planner. Only rows the classifier reads as income count. */
export function IncomeSourcesReport({ budgetId }: Props) {
  const { formatMoney, formatMonth } = useFormatters()
  const moneyAxis = useMoneyAxis()
  const chartHeight = useChartHeight(320)
  const months = useReportMonths()
  const captureRef = useRef<HTMLDivElement>(null)
  const { data, isLoading, isError, error, refetch } = useIncomeBySourceReport(budgetId, months)

  const shown = useMemo(() => (data?.sources ?? []).slice(0, MAX_SERIES), [data])
  const chartData = useMemo(() => {
    if (!data) return []
    return data.months.map((m, i) => {
      const row: Record<string, string | number> = { month: formatMonth(m) }
      for (const s of shown) row[s.payee_name] = s.monthly[i] ?? 0
      const rest = otherIncome(
        data.monthly_totals[i],
        shown.map((s) => s.monthly[i] ?? 0)
      )
      if (rest !== null) row.Other = rest
      return row
    })
  }, [data, shown, formatMonth])

  if (isLoading) return <div className="report-loading">Loading...</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />
  if (!data) return null

  // Served. This divided by `months.length` with the running month in the
  // window, reading 5,500 beside Cost of Living's Take-home of 6,000 for the
  // same steady pay.
  const avg = data.avg_monthly
  const hasOther = chartData.some((r) => 'Other' in r)

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Income by Source</h2>
        <ReportInfoButton title="Income by Source">
          <p>
            Income per payee, month by month. Only rows IGAB reads as income count — transfers
            between your accounts, refunds into an envelope and investment growth are not income.
          </p>
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
                data={chartData}
                margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
                // A payee's month can be negative — a reconciliation
                // adjustment filed to Ready to Assign is income by class. With
                // recharts' default offset ("none") that segment is drawn
                // downwards from the top of the one below it, painting over it
                // and leaving the bar's top at the month's gross rather than
                // its net. "sign" puts negative segments below the axis, where
                // they read as what they are.
                stackOffset="sign"
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
                <Legend />
                {shown.map((s, idx) => (
                  <Bar
                    key={s.payee_id ?? '__none__'}
                    dataKey={s.payee_name}
                    stackId="stack"
                    fill={chartColor(idx)}
                  />
                ))}
                {hasOther && <Bar dataKey="Other" stackId="stack" fill={COLOR_OTHER} />}
              </BarChart>
            </ResponsiveContainer>
          </div>
          <table className="report-table">
            <caption className="sr-only">Income by payee and month</caption>
            <thead>
              <tr>
                <th scope="col" style={{ textAlign: 'left' }}>
                  Source
                </th>
                {data.months.map((m) => (
                  <th key={m} scope="col" style={{ textAlign: 'right' }}>
                    {formatMonth(m)}
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
