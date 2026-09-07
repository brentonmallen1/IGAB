import { useRef } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, XAxis, YAxis } from 'recharts'
import { useReportMonths, useReportStore } from '../../../stores/reportStore'
import { useCostOfLivingReport } from '../../../api/reports'
import { useFormatters } from '../../../hooks/useFormatters'
import { getCurrencySymbol } from '../../../utils/money'
import { ReportErrorState } from '../ReportErrorState'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ReportNotes } from '../ReportNotes'
import type { CostOfLivingGroup } from '../../../types'
import { chartColor } from './chartColors'
import { ReportRangeSelect } from './rangeSelect'

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
  const { formatMoney, settings } = useFormatters()
  const currencySymbol = getCurrencySymbol(settings.currencyCode)
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

  const chartData = data.months.map((monthStr, idx) => {
    const entry: Record<string, string | number> = {
      month: new Date(monthStr).toLocaleDateString('en-US', { month: 'short', year: '2-digit' }),
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
                  tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                  tickFormatter={(v) => `${currencySymbol}${v}`}
                  axisLine={false}
                  tickLine={false}
                />
                <Legend />
                {data.groups.slice(0, 8).map((g, idx) => (
                  <Bar
                    key={g.group_name}
                    dataKey={g.group_name}
                    stackId="stack"
                    fill={chartColor(idx)}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>

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
