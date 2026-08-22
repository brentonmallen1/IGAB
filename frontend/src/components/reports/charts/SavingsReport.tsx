import { useState, useMemo, useRef } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useSavingsReport } from '../../../api/reports'
import { useFormatters } from '../../../hooks/useFormatters'
import { getCurrencySymbol } from '../../../utils/money'
import { ReportErrorState } from '../ReportErrorState'
import { MetricCard } from '../MetricCard'
import { chartColor } from './chartColors'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ChartTooltip } from './ChartTooltip'

interface Props {
  budgetId: string
}

const MONTH_OPTIONS = [6, 12, 24] as const

export function SavingsReport({ budgetId }: Props) {
  const { formatMoney, settings } = useFormatters()
  const currencySymbol = getCurrencySymbol(settings.currencyCode)
  const [months, setMonths] = useState<(typeof MONTH_OPTIONS)[number]>(12)
  const { data, isLoading, isError, error, refetch } = useSavingsReport(budgetId, months)
  const captureRef = useRef<HTMLDivElement>(null)

  const categories = useMemo(() => data?.categories ?? [], [data])
  const summary = data?.summary
  const monthLabels = useMemo(() => data?.months ?? [], [data])

  const chartData = useMemo(() => {
    if (!monthLabels.length || !categories.length) return []

    return monthLabels.map((monthStr, idx) => {
      const date = new Date(monthStr)
      const label = date.toLocaleDateString('en-US', { month: 'short', year: '2-digit' })
      const entry: Record<string, string | number> = { month: label }

      for (const cat of categories) {
        entry[cat.category_name] = cat.monthly_balances[idx] ?? 0
      }

      return entry
    })
  }, [monthLabels, categories])

  if (isLoading) {
    return <div className="report-loading">Loading...</div>
  }
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  const hasData = categories.length > 0

  return (
    <div className="report-section">
      <div className="report-section__header">
        <h2 className="report-section__title">Savings</h2>
        <ReportInfoButton title="Savings">
          <p>
            This report tracks categories you&apos;ve tagged with <strong>Savings</strong> or{' '}
            <strong>Long-term expense</strong>.
          </p>
          <p>
            The chart shows cumulative balances over time. <strong>Total Balance</strong> is the
            sum of all savings category balances. <strong>Avg Monthly Inflow</strong> shows how
            much you&apos;re typically adding.
          </p>
          <p>
            To track a category, go to Settings → Categories and add the Savings tag.
          </p>
          <ReportScopeNote scope="categories" />
        </ReportInfoButton>
        <div className="flex-row">
          {MONTH_OPTIONS.map((m) => (
            <button
              key={m}
              className={`report-btn ${months === m ? 'report-btn--active' : ''}`}
              onClick={() => setMonths(m)}
              type="button"
            >
              {m}mo
            </button>
          ))}
        </div>
        <div style={{ marginLeft: 'auto' }}>
          <ReportExportButton
            reportId="savings"
            getRows={() =>
              categories.map((c) => ({
                category: c.category_name,
                group: c.group_name,
                current_balance: c.current_balance,
                total_inflow: c.total_inflow,
              }))
            }
            captureRef={captureRef}
          />
        </div>
      </div>

      {!hasData ? (
        <div className="reports-empty">
          <p>No savings categories tracked yet.</p>
          <p style={{ fontSize: 'var(--font-size-xs)', marginTop: 8 }}>
            Tag categories with <strong>Savings</strong> or <strong>Long-term expense</strong> to
            track them here.
          </p>
        </div>
      ) : (
        <div ref={captureRef} className="report-capture">
          <div className="report-metrics">
            <MetricCard
              label="Total Balance"
              value={formatMoney(summary?.total_balance ?? 0)}
            />
            <MetricCard
              label="Avg Monthly Inflow"
              value={formatMoney(summary?.avg_monthly_inflow ?? 0)}
            />
            <MetricCard
              label="Categories"
              value={String(summary?.category_count ?? 0)}
              sub="tracked"
            />
          </div>

          <div className="report-chart" style={{ height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                <XAxis
                  dataKey="month"
                  tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                  axisLine={{ stroke: 'var(--border-color)' }}
                  tickLine={false}
                />
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
                {categories.slice(0, 10).map((cat, idx) => (
                  <Area
                    key={cat.category_id}
                    type="monotone"
                    dataKey={cat.category_name}
                    stackId="stack"
                    fill={chartColor(idx)}
                    stroke={chartColor(idx)}
                    fillOpacity={0.6}
                  />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <table className="report-table">
            <caption className="sr-only">Savings category balances</caption>
            <thead>
              <tr>
                <th scope="col" style={{ textAlign: 'left' }}>Category</th>
                <th scope="col" style={{ textAlign: 'left' }}>Group</th>
                <th scope="col" style={{ textAlign: 'right' }}>Balance</th>
                <th scope="col" style={{ textAlign: 'right' }}>Inflow</th>
              </tr>
            </thead>
            <tbody>
              {categories.map((cat) => (
                <tr key={cat.category_id}>
                  <td>{cat.category_name}</td>
                  <td style={{ color: 'var(--text-muted)' }}>{cat.group_name}</td>
                  <td style={{ textAlign: 'right' }}>{formatMoney(cat.current_balance)}</td>
                  <td style={{ textAlign: 'right' }}>{formatMoney(cat.total_inflow)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
