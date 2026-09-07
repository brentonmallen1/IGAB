import { useState, useMemo, useRef } from 'react'
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
import { useSubscriptionsReport } from '../../../api/reports'
import { useFormatters } from '../../../hooks/useFormatters'
import { getCurrencySymbol } from '../../../utils/money'
import { ReportErrorState } from '../ReportErrorState'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { chartColor } from './chartColors'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ChartTooltip } from './ChartTooltip'

interface Props {
  budgetId: string
}

const MONTH_OPTIONS = [6, 12, 24] as const

export function SubscriptionsReport({ budgetId }: Props) {
  const { formatMoney, formatDate, settings } = useFormatters()
  const currencySymbol = getCurrencySymbol(settings.currencyCode)
  const [months, setMonths] = useState<(typeof MONTH_OPTIONS)[number]>(12)
  const { data, isLoading, isError, error, refetch } = useSubscriptionsReport(budgetId, months)
  const captureRef = useRef<HTMLDivElement>(null)

  const subscriptions = useMemo(() => data?.subscriptions ?? [], [data])
  const summary = data?.summary
  const monthLabels = useMemo(() => data?.months ?? [], [data])

  const chartData = useMemo(() => {
    if (!monthLabels.length || !subscriptions.length) return []

    return monthLabels.map((monthStr, idx) => {
      const date = new Date(monthStr)
      const label = date.toLocaleDateString('en-US', { month: 'short', year: '2-digit' })
      const entry: Record<string, string | number> = { month: label }

      for (const sub of subscriptions) {
        entry[sub.payee_name] = sub.monthly_amounts[idx] ?? 0
      }

      return entry
    })
  }, [monthLabels, subscriptions])

  if (isLoading) {
    return <div className="report-loading">Loading...</div>
  }
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  const hasData = subscriptions.length > 0

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Subscriptions</h2>
        <ReportInfoButton title="Subscriptions">
          <p>
            This report shows every charge filed to a category you&apos;ve tagged{' '}
            <strong>Subscription</strong>, listed by payee.
          </p>
          <p>
            To track subscriptions, open the category they are filed to (Streaming, Software…) on
            the Budget page and add the Subscription tag in the panel that opens. The tag is a
            reserved system tag and cannot be deleted.
          </p>
          <p>
            <strong>Monthly (effective)</strong> spreads each subscription's cost over the months
            since its first charge — a quarterly $30 subscription reads as $10/mo.{' '}
            <strong>Per Charge</strong> is the typical amount of a single charge.{' '}
            <strong>Annual</strong> projects the yearly cost from the effective monthly total.
          </p>
          <ReportScopeNote scope="on-budget" />
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
            reportId="subscriptions"
            getRows={() =>
              subscriptions.map((s) => ({
                payee: s.payee_name,
                avg_monthly: s.avg_monthly,
                avg_per_charge: s.avg_per_charge,
                total: s.total,
                transaction_count: s.transaction_count,
                last_charge: s.last_charge_date ?? '',
              }))
            }
            captureRef={captureRef}
          />
        </div>
      </div>

      {!hasData ? (
        <div className="reports-empty">
          <p>No subscriptions tracked yet.</p>
          <p style={{ fontSize: 'var(--font-size-xs)', marginTop: 8 }}>
            Tag the categories your subscriptions are filed to with <strong>Subscription</strong> on
            the Budget page to track recurring charges here.
          </p>
        </div>
      ) : (
        <div ref={captureRef} className="report-capture">
          <MetricRow>
            <MetricCard
              label="Monthly"
              value={formatMoney(summary?.total_monthly ?? 0)}
              sub="effective"
            />
            <MetricCard
              label="Annual"
              value={formatMoney(summary?.total_annual ?? 0)}
              sub="projected"
            />
            <MetricCard
              label="Active"
              value={String(summary?.active_count ?? 0)}
              sub="subscriptions"
            />
          </MetricRow>

          <div className="report-chart" style={{ height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                <XAxis
                  dataKey="month"
                  tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                  axisLine={{ stroke: 'var(--border-color)' }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                  tickFormatter={(v) => `${currencySymbol}${v}`}
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
                {subscriptions.slice(0, 10).map((sub, idx) => (
                  <Bar
                    key={sub.payee_id}
                    dataKey={sub.payee_name}
                    stackId="stack"
                    fill={chartColor(idx)}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>

          <table className="report-table">
            <caption className="sr-only">Recurring charges by payee</caption>
            <thead>
              <tr>
                <th scope="col" style={{ textAlign: 'left' }}>
                  Payee
                </th>
                <th scope="col" style={{ textAlign: 'right' }}>
                  Per Charge
                </th>
                <th scope="col" style={{ textAlign: 'right' }}>
                  Monthly (effective)
                </th>
                <th scope="col" style={{ textAlign: 'right' }}>
                  Total
                </th>
                <th scope="col" style={{ textAlign: 'right' }}>
                  Charges
                </th>
                <th scope="col" style={{ textAlign: 'right' }}>
                  Last Charge
                </th>
              </tr>
            </thead>
            <tbody>
              {subscriptions.map((sub) => (
                <tr key={sub.payee_id}>
                  <td>{sub.payee_name}</td>
                  <td style={{ textAlign: 'right' }}>{formatMoney(sub.avg_per_charge)}</td>
                  <td style={{ textAlign: 'right' }}>{formatMoney(sub.avg_monthly)}</td>
                  <td style={{ textAlign: 'right' }}>{formatMoney(sub.total)}</td>
                  <td style={{ textAlign: 'right' }}>{sub.transaction_count}</td>
                  <td style={{ textAlign: 'right' }}>
                    {sub.last_charge_date ? formatDate(sub.last_charge_date) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
