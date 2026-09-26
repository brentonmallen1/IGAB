import { useRef } from 'react'
import { Link } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useDiscretionaryReport } from '../../../api/reports'
import { useFormatters } from '../../../hooks/useFormatters'
import { useMoneyAxis } from '../../../hooks/useMoneyAxis'
import { sectionHref } from '../../../pages/SettingsPage/settingsSections'
import { useReportMonths, useReportStore } from '../../../stores/reportStore'
import { systemTagName } from '../../settings/TagsPanel/systemTagHelp'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { ReportErrorState } from '../ReportErrorState'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { averagedOver } from './averagedOver'
import { CHART_COLORS, COLOR_NET } from './chartColors'
import { ChartTooltip } from './ChartTooltip'
import {
  discretionaryDrill,
  discretionaryMonthDrill,
  discretionaryRows,
  discretionaryShare,
} from './discretionaryView'
import { ReportRangeSelect } from './rangeSelect'
import './DiscretionaryReport.css'

interface Props {
  budgetId: string
}

/** Where a household tags its categories: the tag list, each with a
 *  chooser for the categories that carry it. */
const TAGS_HREF = sectionHref({ id: 'tags', page: 'settings' })

/**
 * Spending outside Cost of living: what the household chose to spend once the
 * committed bills are set aside.
 *
 * Which rows count is the server's rule (`domain.activity_class
 * .DISCRETIONARY_ROW`); this page lays the served figures out by category
 * within its group, and composes the share of spending in `discretionaryView`.
 * With nothing tagged Essential or Cost of living there is no figure to show —
 * every category would count, and the number would be the whole burn rate —
 * so the page says what to tag instead.
 */
export function DiscretionaryReport({ budgetId }: Props) {
  const { formatMoney, formatMoneyOrDash, formatMonthShort } = useFormatters()
  const moneyAxis = useMoneyAxis()
  const months = useReportMonths()
  const { data, isLoading, isError, error, refetch } = useDiscretionaryReport(budgetId, months)
  const setDrillDown = useReportStore((s) => s.setDrillDown)
  const captureRef = useRef<HTMLDivElement>(null)

  if (isLoading) return <div className="report-loading">Loading...</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />
  if (!data) return null

  const essential = systemTagName('essential')
  const costOfLiving = systemTagName('cost_of_living')
  const report = data
  const rows = discretionaryRows(report.groups, report.total ?? 0)
  const share = discretionaryShare(report)
  const drillWindow = { startDate: report.window_start, endDate: report.window_end }
  const chartData = report.months.map((month, idx) => ({
    month,
    label: formatMonthShort(month),
    Discretionary: report.monthly_totals[idx] ?? 0,
  }))

  // Recharts hands a bar's click either the datum or a wrapper around it.
  function drillMonth(entry: unknown) {
    const d = entry as { month?: string; payload?: { month?: string } }
    const month = d.month ?? d.payload?.month
    if (month)
      setDrillDown(discretionaryMonthDrill(month, `Discretionary · ${formatMonthShort(month)}`))
  }

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Discretionary</h2>
        <ReportInfoButton title="Discretionary">
          <p>
            Spending in categories tagged neither <strong>{essential}</strong> nor{' '}
            <strong>{costOfLiving}</strong> — what you chose to spend once the committed bills are
            set aside. Refunds net against it. Spending with no category counts too, on its own
            line, until you file it.
          </p>
          <p>
            Not the same as <strong>Non-essential</strong> on the Cost of Living report: that is
            committed spending a lean month could shed. Discretionary is everything outside both
            tiers.
          </p>
          <p>
            <strong>Share of spending</strong> is this against all spending over the same months —
            the Expenses on Income vs Expenses. Money moved to savings, debt payments and transfers
            are neither.
          </p>
          <ReportScopeNote report="discretionary" />
        </ReportInfoButton>
        <ReportRangeSelect />
        <div className="ms-auto">
          <ReportExportButton
            reportId="discretionary"
            getRows={() =>
              rows.map((r) => ({
                line: r.label,
                kind: r.kind,
                avg_monthly: r.avgMonthly,
                total: r.total,
                share: r.share,
              }))
            }
            captureRef={captureRef}
            window={{ start: report.window_start, end: report.window_end }}
          />
        </div>
      </div>

      {!report.tagged ? (
        <div className="discretionary-report__empty">
          <p>
            Discretionary is the spending outside <strong>{essential}</strong> and{' '}
            <strong>{costOfLiving}</strong>. Nothing carries either tag yet, so every category would
            count here, and the figure would be all of your spending rather than the part you chose.
          </p>
          <p>
            <Link to={TAGS_HREF}>Tag your committed categories in Settings → Tags</Link> — rent and
            utilities as {essential}, subscriptions and memberships as {costOfLiving} — and this
            report fills in with the rest.
          </p>
        </div>
      ) : rows.length === 0 ? (
        <div className="reports-empty">
          <p>No discretionary spending in this window.</p>
        </div>
      ) : (
        <div ref={captureRef} className="report-capture">
          <MetricRow>
            <MetricCard
              label="Discretionary"
              value={formatMoneyOrDash(report.avg_monthly)}
              sub={averagedOver('per month', report.months_averaged)}
            />
            <MetricCard
              label="Window total"
              value={formatMoneyOrDash(report.total)}
              sub={`${formatMonthShort(report.window_start)} – ${formatMonthShort(report.window_end)}`}
            />
            {/* Null is "no spending on record", which is not 0% and not 100%. */}
            <MetricCard
              label="Share of spending"
              value={share === null ? '—' : `${Math.round(share)}%`}
              sub={
                share === null
                  ? 'no spending on record'
                  : `of ${formatMoneyOrDash(report.spending_total)} spent`
              }
            />
          </MetricRow>

          {/* One series against its own average: the question is which months
              ran over, and a bar opens that month's rows. */}
          <div className="report-chart">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={chartData} margin={{ top: 16, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="var(--border-color)"
                  vertical={false}
                />
                <XAxis
                  dataKey="label"
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
                  content={<ChartTooltip formatter={formatMoney} />}
                  offset={16}
                  isAnimationActive={false}
                  cursor={{ fill: 'var(--row-hover-bg)' }}
                />
                {report.avg_monthly !== null && (
                  <ReferenceLine
                    y={report.avg_monthly}
                    stroke={COLOR_NET}
                    strokeDasharray="6 3"
                    label={{
                      value: `Per month: ${formatMoney(report.avg_monthly)}`,
                      position: 'insideTopRight',
                      fill: 'var(--text-secondary)',
                      fontSize: 11,
                    }}
                  />
                )}
                <Bar
                  dataKey="Discretionary"
                  fill={CHART_COLORS[0]}
                  radius={[2, 2, 0, 0]}
                  isAnimationActive={false}
                  cursor="pointer"
                  onClick={drillMonth}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <table className="report-table discretionary-report__table">
            <caption className="sr-only">Discretionary spending by category</caption>
            <thead>
              <tr>
                <th scope="col" className="discretionary-report__name">
                  Category
                </th>
                <th scope="col" className="discretionary-report__num">
                  Monthly
                </th>
                <th scope="col" className="discretionary-report__num">
                  Total
                </th>
                <th scope="col" className="discretionary-report__num">
                  Share
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key} className={`discretionary-report__row--${r.kind}`}>
                  <td>
                    {/* A button, not a clickable row, so every line opens from
                        the keyboard too. */}
                    <button
                      type="button"
                      className="report-table__drill"
                      onClick={() => setDrillDown(discretionaryDrill(r, drillWindow))}
                      aria-label={`Show the transactions behind ${r.label}`}
                    >
                      {r.label}
                    </button>
                  </td>
                  <td className="discretionary-report__num tabular">{formatMoney(r.avgMonthly)}</td>
                  <td className="discretionary-report__num tabular">{formatMoney(r.total)}</td>
                  <td className="discretionary-report__num tabular">
                    {r.share === null ? '—' : `${Math.round(r.share)}%`}
                  </td>
                </tr>
              ))}
            </tbody>
            {/* The groups' own sum, and the headline: one figure. */}
            <tfoot>
              <tr>
                <td>Total</td>
                <td className="discretionary-report__num tabular">
                  {formatMoneyOrDash(report.avg_monthly)}
                </td>
                <td className="discretionary-report__num tabular">
                  {formatMoneyOrDash(report.total)}
                </td>
                <td />
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  )
}
