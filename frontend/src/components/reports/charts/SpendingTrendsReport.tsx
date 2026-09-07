import { useMemo, useRef, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
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
import { getCurrencySymbol } from '../../../utils/money'
import { ReportErrorState } from '../ReportErrorState'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ChartTooltip } from './ChartTooltip'
import { chartColor } from './chartColors'
import { rollupTrends } from './spendingTrends'
import { useReportScope } from '../../../stores/reportStore'

interface Props {
  budgetId: string
}

const MAX_SERIES = 10

/**
 * Spending over time for a chosen set of categories — the basic report that
 * was missing. Scope is the shared category filter, plus a saved filter and
 * tags of its own; the server resolves the union, so a saved filter that
 * follows a tag follows it here too.
 */
export function SpendingTrendsReport({ budgetId }: Props) {
  const { formatMoney, formatMonth } = useFormatters()
  const { settings } = useFormatters()
  const currencySymbol = getCurrencySymbol(settings.currencyCode)
  const chartHeight = useChartHeight(340)
  const { filters } = useReportStore()
  const groupBy = resolveGroupBy('spending-trends', filters.groupBy)
  const [includeSavings, setIncludeSavings] = useState(false)
  const [chart, setChart] = useState<'stacked' | 'lines'>('stacked')
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
  const shown = rolled.slice(0, MAX_SERIES)
  const chartData = useMemo(() => {
    if (!data) return []
    return data.months.map((m, i) => {
      const row: Record<string, string | number> = { month: formatMonth(m) }
      for (const s of shown) row[s.name] = s.monthly[i] ?? 0
      return row
    })
  }, [data, shown, formatMonth])

  if (isLoading) return <div className="report-loading">Loading...</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />
  if (!data) return null

  const avg = data.months.length ? data.total / data.months.length : 0
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
          <ReportScopeNote scope="categories" />
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
          <label className="report-toggle">
            <input
              type="checkbox"
              checked={includeSavings}
              onChange={(e) => setIncludeSavings(e.target.checked)}
            />
            Include savings &amp; debt payments
          </label>
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

      {data.filter_unavailable && (
        <p className="report-note">That saved filter no longer exists; showing everything.</p>
      )}
      {data.class_excluded.length > 0 && !includeSavings && (
        <p className="report-note">
          Left out of this scope:{' '}
          {data.class_excluded
            .map(
              (c) =>
                `${c.label} ${formatMoney(c.total)} in ${c.categories} categor${c.categories === 1 ? 'y' : 'ies'}`
            )
            .join('; ')}
          .
        </p>
      )}

      {rolled.length === 0 ? (
        <div className="reports-empty">
          <p>Nothing spent in this scope over the window.</p>
        </div>
      ) : (
        <div ref={captureRef} className="report-capture">
          <MetricRow>
            <MetricCard label="Total" value={formatMoney(data.total)} />
            <MetricCard label="Average / month" value={formatMoney(avg)} />
            <MetricCard label="Latest month" value={formatMoney(last)} />
          </MetricRow>

          <div className="report-chart" style={{ height: chartHeight }}>
            <ResponsiveContainer width="100%" height="100%">
              {chart === 'stacked' ? (
                <BarChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                  <XAxis dataKey="month" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
                  <YAxis
                    tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                    tickFormatter={(v) =>
                      Math.abs(v) >= 1000
                        ? `${currencySymbol}${Math.round(v / 1000)}k`
                        : `${currencySymbol}${Math.round(v)}`
                    }
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
                      />
                    )}
                  />
                  <Legend />
                  {shown.map((s, idx) => (
                    <Bar key={s.key} dataKey={s.name} stackId="stack" fill={chartColor(idx)} />
                  ))}
                </BarChart>
              ) : (
                <LineChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                  <XAxis dataKey="month" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
                  <YAxis
                    tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                    tickFormatter={(v) =>
                      Math.abs(v) >= 1000
                        ? `${currencySymbol}${Math.round(v / 1000)}k`
                        : `${currencySymbol}${Math.round(v)}`
                    }
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
                      />
                    )}
                  />
                  <Legend />
                  {shown.map((s, idx) => (
                    <Line
                      key={s.key}
                      type="monotone"
                      dataKey={s.name}
                      stroke={chartColor(idx)}
                      dot={false}
                      strokeWidth={2}
                    />
                  ))}
                </LineChart>
              )}
            </ResponsiveContainer>
          </div>

          <table className="report-table">
            <caption className="sr-only">Spending by month</caption>
            <thead>
              <tr>
                <th scope="col" style={{ textAlign: 'left' }}>
                  {groupBy === 'group' ? 'Group' : 'Category'}
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
