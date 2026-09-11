import { Fragment, useState, useMemo, useRef } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
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
import { ReportErrorState } from '../ReportErrorState'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { chartColor } from './chartColors'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ChartTooltip } from './ChartTooltip'
import { ReportRangeSelect } from './rangeSelect'
import { useReportMonths } from '../../../stores/reportStore'
import { useMoneyAxis } from './useMoneyAxis'

interface Props {
  budgetId: string
}

export function SubscriptionsReport({ budgetId }: Props) {
  const { formatMoney, formatDate, formatMonthShort } = useFormatters()
  const moneyAxis = useMoneyAxis()
  const months = useReportMonths()
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const { data, isLoading, isError, error, refetch } = useSubscriptionsReport(budgetId, months)
  const captureRef = useRef<HTMLDivElement>(null)

  const subscriptions = useMemo(() => data?.subscriptions ?? [], [data])
  const summary = data?.summary
  const monthLabels = useMemo(() => data?.months ?? [], [data])

  const chartData = useMemo(() => {
    if (!monthLabels.length || !subscriptions.length) return []

    return monthLabels.map((monthStr, idx) => {
      const entry: Record<string, string | number> = { month: formatMonthShort(monthStr) }

      for (const sub of subscriptions) {
        entry[sub.category_name] = sub.monthly_amounts[idx] ?? 0
      }

      return entry
    })
  }, [monthLabels, subscriptions, formatMonthShort])

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
            <strong>Subscription</strong>, one line per category. Open a row to see which services
            inside it are charging.
          </p>
          <p>
            To track subscriptions, open the category they are filed to (Streaming, Software…) on
            the Budget page and add the Subscription tag in the panel that opens. The tag is a
            reserved system tag and cannot be deleted.
          </p>
          <p>
            <strong>Monthly (effective)</strong> spreads each subscription's cost over the COMPLETE
            months since its first charge — a quarterly $30 subscription reads as about $10/mo. The
            month in progress is left out of that divisor, or every figure here would read at its
            lowest on the 2nd of the month and <strong>Annual</strong> would multiply that by
            twelve. <strong>Per Charge</strong> is the typical amount of a single charge.
          </p>
          <ReportScopeNote scope="on-budget" />
        </ReportInfoButton>
        <ReportRangeSelect />
        <div style={{ marginLeft: 'auto' }}>
          <ReportExportButton
            reportId="subscriptions"
            getRows={() =>
              // Both levels, flat: a spreadsheet wants the services as rows
              // too, and the category column is what groups them there.
              subscriptions.flatMap((s) => [
                {
                  category: s.category_name,
                  payee: '',
                  avg_monthly: s.avg_monthly,
                  avg_per_charge: s.avg_per_charge,
                  total: s.total,
                  transaction_count: s.transaction_count,
                  last_charge: s.last_charge_date ?? '',
                },
                ...s.payees.map((p) => ({
                  category: s.category_name,
                  payee: p.payee_name,
                  avg_monthly: p.avg_monthly,
                  avg_per_charge: p.avg_per_charge,
                  total: p.total,
                  transaction_count: p.transaction_count,
                  last_charge: p.last_charge_date ?? '',
                })),
              ])
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
              sub={
                data && data.months_averaged < monthLabels.length
                  ? `effective, over ${data.months_averaged} complete months`
                  : 'effective'
              }
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
                <Legend />
                {subscriptions.slice(0, 10).map((sub, idx) => (
                  <Bar
                    key={sub.category_id}
                    dataKey={sub.category_name}
                    stackId="stack"
                    fill={chartColor(idx)}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>

          <table className="report-table">
            <caption className="sr-only">
              Recurring charges by category, expandable to the payees inside each one
            </caption>
            <thead>
              <tr>
                <th scope="col" style={{ textAlign: 'left' }}>
                  Category
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
              {subscriptions.map((sub) => {
                const open = expanded.has(sub.category_id)
                return (
                  <Fragment key={sub.category_id}>
                    <tr>
                      <td>
                        <button
                          type="button"
                          className="subs-report__disclose"
                          aria-expanded={open}
                          onClick={() =>
                            setExpanded((prev) => {
                              const next = new Set(prev)
                              if (!next.delete(sub.category_id)) next.add(sub.category_id)
                              return next
                            })
                          }
                        >
                          {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                          {sub.category_name}
                          <span className="subs-report__group">{sub.group_name}</span>
                        </button>
                      </td>
                      <td style={{ textAlign: 'right' }}>{formatMoney(sub.avg_per_charge)}</td>
                      <td style={{ textAlign: 'right' }}>{formatMoney(sub.avg_monthly)}</td>
                      <td style={{ textAlign: 'right' }}>{formatMoney(sub.total)}</td>
                      <td style={{ textAlign: 'right' }}>{sub.transaction_count}</td>
                      <td style={{ textAlign: 'right' }}>
                        {sub.last_charge_date ? formatDate(sub.last_charge_date) : '—'}
                      </td>
                    </tr>
                    {open &&
                      sub.payees.map((p) => (
                        <tr key={p.payee_id ?? '__none__'} className="subs-report__payee">
                          <td>{p.payee_name}</td>
                          <td style={{ textAlign: 'right' }}>{formatMoney(p.avg_per_charge)}</td>
                          <td style={{ textAlign: 'right' }}>{formatMoney(p.avg_monthly)}</td>
                          <td style={{ textAlign: 'right' }}>{formatMoney(p.total)}</td>
                          <td style={{ textAlign: 'right' }}>{p.transaction_count}</td>
                          <td style={{ textAlign: 'right' }}>
                            {p.last_charge_date ? formatDate(p.last_charge_date) : '—'}
                          </td>
                        </tr>
                      ))}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
