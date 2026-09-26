import { Fragment, useState, useMemo, useRef } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useSubscriptionsReport } from '../../../api/reports'
import { useFormatters } from '../../../hooks/useFormatters'
import { ReportErrorState } from '../ReportErrorState'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ChartTooltip } from './ChartTooltip'
import { ChartLegend } from './ChartLegend'
import { ReportRangeSelect } from './rangeSelect'
import { useReportMonths, useReportStore } from '../../../stores/reportStore'
import { useMoneyAxis } from '../../../hooks/useMoneyAxis'
import { MIXED_SIGN_STACK } from './mixedSignStack'
import { stackTrends } from './spendingTrends'
import {
  activeCard,
  annualSub,
  basisNote,
  cadenceLabel,
  serviceDrill,
  subscriptionTrendRows,
} from './subscriptionsView'
import './SubscriptionsReport.css'

interface Props {
  budgetId: string
}

export function SubscriptionsReport({ budgetId }: Props) {
  const { formatMoney, formatDate, formatMonthShort } = useFormatters()
  const moneyAxis = useMoneyAxis()
  const months = useReportMonths()
  const setDrillDown = useReportStore((s) => s.setDrillDown)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  // Which series the legend points at: the palette repeats past eight.
  const [highlight, setHighlight] = useState<string | null>(null)
  const { data, isLoading, isError, error, refetch } = useSubscriptionsReport(budgetId, months)
  const captureRef = useRef<HTMLDivElement>(null)

  const subscriptions = useMemo(() => data?.subscriptions ?? [], [data])
  // Ten categories by name and an Other band, so every bar stands at its
  // month's served total — the chart stacked the ten largest and dropped the
  // rest, under recharts' own legend of chips.
  const stacked = useMemo(
    () =>
      data
        ? stackTrends(data, subscriptionTrendRows(data.subscriptions), formatMonthShort)
        : { rows: [], series: [] },
    [data, formatMonthShort]
  )

  if (isLoading) {
    return <div className="report-loading">Loading...</div>
  }
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  const hasData = subscriptions.length > 0
  const summary = data?.summary
  const active = summary ? activeCard(summary) : null

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Subscriptions</h2>
        <ReportInfoButton title="Subscriptions">
          <p>
            Every charge filed to a category you&apos;ve tagged <strong>Subscription</strong>, one
            line per category. Open a row to see the services inside it; click a service to list its
            charges.
          </p>
          <p>
            <strong>Annual</strong> is what each service charged over the last 12 complete months,
            less refunds — whatever range you pick, which moves only the chart.{' '}
            <strong>Monthly</strong> is Annual ÷ 12. Two kinds of service are projected instead,
            from their latest charge: one first charged within the year (latest charge × the charges
            a year its cadence makes — a single charge has no cadence yet, so it counts once), and
            one whose new price has been charged twice (the year&apos;s charges at the new price).
          </p>
          <p>
            A service with no charge for one and a half cycles — two weeks late on a monthly bill,
            six months on a yearly one — is <strong>stopped</strong>: still listed, counted in
            nothing. Cash Projection stops projecting it by the same rule.
          </p>
          <p>
            To track subscriptions, open the category they are filed to on the Budget page and add
            the Subscription tag.
          </p>
          <ReportScopeNote report="subscriptions" />
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
                  service: '',
                  basis: '',
                  cadence: '',
                  latest_charge: '',
                  monthly: s.monthly,
                  annual: s.annual,
                  last_charge: s.last_charge_date,
                },
                ...s.services.map((v) => ({
                  category: s.category_name,
                  service: v.payee_name,
                  basis: v.basis,
                  cadence: cadenceLabel(v),
                  latest_charge: v.latest_charge,
                  monthly: v.monthly,
                  annual: v.annual,
                  last_charge: v.last_charge_date,
                })),
              ])
            }
            captureRef={captureRef}
          />
        </div>
      </div>

      {!hasData || !data || !summary || !active ? (
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
              value={formatMoney(summary.total_monthly)}
              sub="Annual ÷ 12"
            />
            <MetricCard
              label="Annual"
              value={formatMoney(summary.total_annual)}
              sub={annualSub(summary)}
            />
            <MetricCard label="Active" value={active.value} sub={active.sub} />
          </MetricRow>

          <div className="report-chart" style={{ height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={stacked.rows}
                {...MIXED_SIGN_STACK}
                margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
              >
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
                  content={({ active: on, payload, label }) => (
                    <ChartTooltip
                      active={on}
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
            <caption className="sr-only">
              What each subscription costs, by category, expandable to the services inside
            </caption>
            <thead>
              <tr>
                <th scope="col" style={{ textAlign: 'left' }}>
                  Category
                </th>
                <th scope="col" style={{ textAlign: 'left' }}>
                  Every
                </th>
                <th scope="col" style={{ textAlign: 'right' }}>
                  Latest
                </th>
                <th scope="col" style={{ textAlign: 'right' }}>
                  Monthly
                </th>
                <th scope="col" style={{ textAlign: 'right' }}>
                  Annual
                </th>
                <th scope="col" style={{ textAlign: 'right' }}>
                  Last charge
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
                      <td />
                      <td />
                      <td className="tabular" style={{ textAlign: 'right' }}>
                        {formatMoney(sub.monthly)}
                      </td>
                      <td className="tabular" style={{ textAlign: 'right' }}>
                        {formatMoney(sub.annual)}
                      </td>
                      <td style={{ textAlign: 'right' }}>{formatDate(sub.last_charge_date)}</td>
                    </tr>
                    {open &&
                      sub.services.map((v) => {
                        const drill = serviceDrill(sub, v, data)
                        const note = basisNote(v)
                        return (
                          <tr
                            key={v.payee_id ?? '__none__'}
                            className={`subs-report__service${v.basis === 'stopped' ? ' is-stopped' : ''}`}
                          >
                            <td>
                              {drill ? (
                                <button
                                  type="button"
                                  className="subs-report__drill"
                                  onClick={() => setDrillDown(drill)}
                                  aria-label={`List charges from ${v.payee_name}`}
                                >
                                  {v.payee_name}
                                </button>
                              ) : (
                                v.payee_name
                              )}
                              {note && <span className="subs-report__note">{note}</span>}
                            </td>
                            <td>{cadenceLabel(v)}</td>
                            <td className="tabular" style={{ textAlign: 'right' }}>
                              {formatMoney(v.latest_charge)}
                            </td>
                            <td className="tabular" style={{ textAlign: 'right' }}>
                              {formatMoney(v.monthly)}
                            </td>
                            <td className="tabular" style={{ textAlign: 'right' }}>
                              {formatMoney(v.annual)}
                            </td>
                            <td style={{ textAlign: 'right' }}>{formatDate(v.last_charge_date)}</td>
                          </tr>
                        )
                      })}
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
