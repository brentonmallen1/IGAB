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

interface Props {
  budgetId: string
}

/**
 * What it costs to keep the lights on, by category group.
 *
 * Built on the Essential tag rather than a new "utilities" one: a sixth
 * system tag whose only job is grouping would be a permanent addition to a
 * vocabulary that otherwise changes how money is COUNTED, and the groups a
 * budget already has are the shape a household thinks in.
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
      uncategorized: uncategorized || undefined,
      activityClasses: report.counted_classes,
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
            Your <strong>essential</strong> spending, grouped the way your budget already is —
            Housing, Utilities, Groceries — so you can see what a month costs before anything
            discretionary.
          </p>
          <p>
            &ldquo;Essential&rdquo; is whatever you told the Guide, or whatever carries the{' '}
            <strong>Essential</strong> tag. Tag a category from its panel on the Budget page.
          </p>
          <p>
            <strong>Required ratio</strong> is the share of take-home already spoken for. Each
            group&apos;s share is of the essentials total, not of income, so the shares add to 100%.
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
          Nothing is tagged <strong>Essential</strong> yet, so this counts every category — which is
          your whole burn rate, not your cost of living. Tag the categories you could not stop
          paying and this becomes a different number.
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
            <MetricCard
              label="Essentials"
              value={formatMoney(data.avg_monthly_essentials)}
              sub="per month"
            />
            <MetricCard
              label="Take-home"
              value={formatMoney(data.avg_monthly_income)}
              sub="per month"
            />
            <MetricCard
              label="Required"
              // Null is "we have no income on record", which is not 0% and
              // not 100% — saying either would be inventing a ratio.
              value={data.required_ratio === null ? '—' : `${Math.round(data.required_ratio)}%`}
              sub={data.required_ratio === null ? 'no income on record' : 'of take-home'}
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
            <caption className="sr-only">Essential spending by category group</caption>
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
