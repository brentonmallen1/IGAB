import { useRef, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useReportMonths, useReportStore } from '../../../stores/reportStore'
import { useCostOfLivingReport } from '../../../api/reports'
import { useFormatters } from '../../../hooks/useFormatters'
import { ReportErrorState } from '../ReportErrorState'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ReportNotes } from '../ReportNotes'
import type { CostOfLivingGroup } from '../../../types'
import { chartColor } from './chartColors'
import { ChartLegend } from './ChartLegend'
import { ChartTooltip } from './ChartTooltip'
import { ReportRangeSelect } from './rangeSelect'
import { useMoneyAxis } from './useMoneyAxis'
import { necessityReading, sheddableShare } from './necessityView'
import { averagedOver } from './averagedOver'

interface Props {
  budgetId: string
}

/**
 * What it costs to keep the lights on, by category group, in two tiers.
 *
 * The table and chart roll up the WIDE tier: categories tagged Essential or
 * Cost of living, plus debt payments by class. The Essentials card is the
 * lean tier inside it, and Non-essential is the gap — what a lean month could
 * shed. Which rows each tier holds is the server's rule
 * (`domain.activity_class.tier_scope`); this page only lays the figures out,
 * in the groups a budget already has, which are the shape a household
 * thinks in.
 */
/** The null-group bucket's name, which the server also spells. A drill into it
 *  means "rows with no category" — an empty id list filters nothing and would
 *  open a panel listing the whole window. */
const UNCATEGORIZED = 'Uncategorized'

export function CostOfLivingReport({ budgetId }: Props) {
  const { formatMoney, formatMonthShort } = useFormatters()
  const moneyAxis = useMoneyAxis()
  // Which group the legend is pointing at, if any. The palette repeats past
  // eight slots, so this is what tells two same-coloured bands apart.
  const [highlight, setHighlight] = useState<string | null>(null)
  const months = useReportMonths()
  const { data, isLoading, isError, error, refetch } = useCostOfLivingReport(budgetId, months)
  const setDrillDown = useReportStore((s) => s.setDrillDown)
  const captureRef = useRef<HTMLDivElement>(null)

  if (isLoading) return <div className="report-loading">Loading...</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />
  if (!data) return null

  const reading = necessityReading(data.required_ratio, data.essentials_ratio)
  const sheddable = sheddableShare(data.avg_monthly_cost_of_living, data.avg_monthly_non_essential)
  // The window is complete months only, and the card says how many — the
  // difference between a figure a reader can check and one that just looks
  // low at the start of a month.
  const perMonth = averagedOver('per month', data.months_averaged)

  const report = data

  /**
   * Open a group's rows.
   *
   * Window and counted classes both come from the response, so the panel
   * totals what the bar says rather than every row of the same sign. This
   * report had no drill-down at all, and a $30,000 YNAB closing adjustment
   * landing in Uncategorized was therefore unexplainable from the page —
   * which is indistinguishable from the report being wrong.
   */
  function drillTo(g: CostOfLivingGroup) {
    const uncategorized = g.group_name === UNCATEGORIZED
    if (!uncategorized && g.category_ids.length === 0) return
    setDrillDown({
      kind: 'category-group',
      label: g.group_name,
      // Categories live on split children, so a category-keyed drill counts
      // leaves — the scope the report's own query uses.
      scope: 'leaf',
      categoryIds: uncategorized ? undefined : g.category_ids,
      noCategory: uncategorized || undefined,
      activityClasses: report.counted_classes,
      // Debt principal joins the tier by class, per row: without the tier a
      // bar's categories list the fuel beside the loan payment it counted.
      necessityTier: report.necessity_tier,
      startDate: report.window_start,
      endDate: report.window_end,
    })
  }

  // Every group is drawn. Capping the bars at eight left the stack short by
  // whatever it dropped while the table below listed the lot, so one screen
  // said two different things about what a month cost.
  //
  // The palette repeats past its eighth slot, so identity moves to the legend:
  // it lists the groups in stack order and dims the rest on hover. That is
  // what makes a repeated colour unambiguous rather than merely tolerated.
  const chartData = data.months.map((monthStr, idx) => {
    const entry: Record<string, string | number> = {
      month: formatMonthShort(monthStr),
    }
    for (const g of data.groups) entry[g.group_name] = g.monthly_amounts[idx] ?? 0
    return entry
  })

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Cost of Living</h2>
        <ReportInfoButton title="Cost of Living">
          <p>
            Everything that leaves your account whether or not you feel like it, grouped the way
            your budget already is. Two tiers sit inside it: <strong>Essentials</strong> are the
            things you could not cut, and <strong>Non-essential</strong> is the rest — committed,
            but sheddable in a genuine emergency.
          </p>
          <p>
            Tag a category <strong>Essential</strong> or <strong>Cost of living</strong> from its
            panel on the Budget page. Debt payments count here without any tag at all, so a
            household with a loan sees a truthful figure straight away.
          </p>
          <p>
            <strong>Required</strong> is the share of take-home already spoken for. Both figures
            cover the same window, which is what makes the difference between them a real number.
            Each group&apos;s share is of the cost-of-living total, not of income, so the shares add
            to 100%.
          </p>
          <ReportScopeNote scope="on-budget" />
        </ReportInfoButton>
        <ReportRangeSelect />
        <div style={{ marginLeft: 'auto' }}>
          <ReportExportButton
            reportId="cost-of-living"
            getRows={() =>
              data.groups.map((g) => ({
                group: g.group_name,
                avg_monthly: g.avg_monthly,
                total: g.total,
                share: g.share,
              }))
            }
            captureRef={captureRef}
          />
        </div>
      </div>

      {!data.tagged && (
        <p className="reports-note">
          Nothing is tagged <strong>Essential</strong> or <strong>Cost of living</strong> yet, so
          this counts every category — which is your whole burn rate, not your cost of living. Tag
          the ones you could not stop paying and this becomes a different number.
        </p>
      )}

      {/* What was tagged and still not counted. This report counts debt
          payments, so the sentence must not say "spending": a mortgage IS
          here now, and a category tagged both Essential and Savings is not. */}
      <ReportNotes report={data} toggleAvailable={false} counts="a cost of living" />

      {data.groups.length === 0 ? (
        <div className="reports-empty">
          <p>No spending in this window.</p>
        </div>
      ) : (
        <div ref={captureRef} className="report-capture">
          <MetricRow>
            {/* "per complete month", because that is the divisor. The
                averages used to divide by the whole window with its newest
                month still running, which put this report's figure below the
                Essentials report's for the same tag and the same query. */}
            <MetricCard
              label="Cost of living"
              value={formatMoney(data.avg_monthly_cost_of_living)}
              sub={perMonth}
            />
            {/* Null until something is tagged Essential: all spending is not
                what a household could not cut, so the figure is unknown. */}
            <MetricCard
              label="Essentials"
              value={
                data.avg_monthly_essentials === null
                  ? '—'
                  : formatMoney(data.avg_monthly_essentials)
              }
              sub={
                data.avg_monthly_essentials === null
                  ? 'nothing tagged Essential'
                  : 'could not be cut'
              }
            />
            {/* Named for what it IS, not for what to do about it. "Could cut"
                beside a household's car payment reads as advice to sell the
                car; this is an inventory, and the note below says so. */}
            <MetricCard
              label="Non-essential"
              value={
                data.avg_monthly_non_essential === null
                  ? '—'
                  : formatMoney(data.avg_monthly_non_essential)
              }
              sub={
                data.avg_monthly_non_essential === null
                  ? 'needs Essentials tagged'
                  : sheddable === null
                    ? 'nothing committed yet'
                    : `${Math.round(sheddable)}% of the above`
              }
            />
            <MetricCard
              label="Take-home"
              value={formatMoney(data.avg_monthly_income)}
              sub={perMonth}
            />
            <MetricCard
              label="Required"
              // Null is "we have no income on record", which is not 0% and
              // not 100% — saying either would be inventing a ratio.
              value={data.required_ratio === null ? '—' : `${Math.round(data.required_ratio)}%`}
              sub={data.required_ratio === null ? 'no income on record' : 'of take-home'}
            />
          </MetricRow>

          <p className={`reports-note necessity-standing--${reading.standing}`}>{reading.note}</p>

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
                {/* `shared={false}` names the ONE band under the cursor.
                    Shared, a stacked chart lists every group for that month —
                    twelve rows to answer "what is this block", which is the
                    same overwhelm the legend was fixed for. It is also what
                    makes a repeated colour readable from the chart side: the
                    legend resolves group→band, this resolves band→group. */}
                <Tooltip
                  shared={false}
                  content={<ChartTooltip formatter={formatMoney} />}
                  offset={16}
                  isAnimationActive={false}
                  cursor={{ fill: 'var(--row-hover-bg)' }}
                />
                {data.groups.map((g, idx) => (
                  <Bar
                    key={g.group_name}
                    dataKey={g.group_name}
                    stackId="stack"
                    fill={chartColor(idx)}
                    fillOpacity={highlight && highlight !== g.group_name ? 0.25 : 1}
                    isAnimationActive={false}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>

          <ChartLegend
            series={data.groups.map((g, idx) => ({
              name: g.group_name,
              color: chartColor(idx),
              value: formatMoney(g.avg_monthly),
            }))}
            active={highlight}
            onHover={setHighlight}
          />

          <table className="report-table">
            <caption className="sr-only">Cost of living by category group</caption>
            <thead>
              <tr>
                <th scope="col" style={{ textAlign: 'left' }}>
                  Group
                </th>
                <th scope="col" style={{ textAlign: 'right' }}>
                  Monthly
                </th>
                <th scope="col" style={{ textAlign: 'right' }}>
                  Total
                </th>
                <th scope="col" style={{ textAlign: 'right' }}>
                  Share
                </th>
              </tr>
            </thead>
            <tbody>
              {data.groups.map((g) => (
                <tr key={g.group_name}>
                  <td>
                    {/* A button, not a clickable row: this is the bucket a
                        reader most needs to open, and a row reachable only by
                        mouse is not an answer for everyone. */}
                    <button
                      type="button"
                      className="report-table__drill"
                      onClick={() => drillTo(g)}
                      aria-label={`Show the transactions behind ${g.group_name}`}
                    >
                      {g.group_name}
                    </button>
                  </td>
                  <td style={{ textAlign: 'right' }}>{formatMoney(g.avg_monthly)}</td>
                  <td style={{ textAlign: 'right' }}>{formatMoney(g.total)}</td>
                  <td style={{ textAlign: 'right' }}>{Math.round(g.share)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
