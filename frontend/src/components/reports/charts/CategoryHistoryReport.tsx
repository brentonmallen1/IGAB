import { useMemo, useRef, useState } from 'react'
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useCategoryHistoryReport } from '../../../api/reports'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import { useFormatters } from '../../../hooks/useFormatters'
import { useChartHeight } from '../../../hooks/useChartHeight'
import { groupedCategorySections } from '../../../utils/categoryPickers'
import { GroupedCategoryOptions } from '../../common/GroupedCategoryOptions/GroupedCategoryOptions'
import { ReportErrorState } from '../ReportErrorState'
import { ReportRangeSelect } from './rangeSelect'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { ReportInfoButton } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ChartTooltip } from './ChartTooltip'
import { COLOR_NEGATIVE, COLOR_NET, COLOR_POSITIVE } from './chartColors'
import { useReportMonths } from '../../../stores/reportStore'
import { useMoneyAxis } from '../../../hooks/useMoneyAxis'
import {
  completeMonthRows,
  monthRange,
  reportMonthLabel,
  RUNNING_MONTH_OPACITY,
} from '../../../utils/reportMonths'
import { fromCents, sumToCents } from '../../../utils/money'
import { completeMonths } from './averagedOver'

interface Props {
  budgetId: string
}

/** One category, month by month: assigned, spent, and what was left — the
 *  budget page's own figures, from the same service. */
export function CategoryHistoryReport({ budgetId }: Props) {
  const { formatMoney, formatMoneyOrDash, formatMonthShort } = useFormatters()
  const moneyAxis = useMoneyAxis()
  const chartHeight = useChartHeight(320)
  const [categoryId, setCategoryId] = useState('')
  const months = useReportMonths()
  const captureRef = useRef<HTMLDivElement>(null)
  const { data: categories = [] } = useCategories(budgetId)
  const { data: groups = [] } = useCategoryGroups(budgetId)
  const sections = useMemo(
    () =>
      groupedCategorySections(
        categories.filter((c) => c.is_categorizable),
        groups
      ),
    [categories, groups]
  )
  const { data, isLoading, isError, error, refetch } = useCategoryHistoryReport(
    budgetId,
    categoryId || null,
    months
  )

  const chartData = useMemo(
    () =>
      (data?.months ?? []).map((m) => ({
        iso: m.month,
        month: reportMonthLabel(m.month, m.partial_month, formatMonthShort),
        partial: m.partial_month,
        Assigned: m.assigned,
        Spent: Math.abs(Math.min(m.activity, 0)),
        // Null for an income category: no line rather than a false one.
        Available: m.available ?? undefined,
      })),
    [data, formatMonthShort]
  )

  const rows = data?.months ?? []
  // An em dash for an income category, which holds no money — its
  // `available` is a lifetime carryover the budget page never draws.
  const latestAvailable = rows[rows.length - 1]?.available ?? null
  const availableNow = formatMoneyOrDash(latestAvailable)

  // The cards read complete months only: the running month's plan is all in
  // from the 1st while its spending arrives over the month, and averaging it
  // in read every category low at the start of a month.
  const complete = completeMonthRows(rows)
  const spent = fromCents(sumToCents(complete.map((m) => Math.abs(Math.min(m.activity, 0)))))
  const assigned = fromCents(sumToCents(complete.map((m) => m.assigned)))
  const covered = monthRange(complete[0]?.month, complete.at(-1)?.month, formatMonthShort)
  const over = covered ?? `over ${completeMonths(complete.length)}`

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Category History</h2>
        <ReportInfoButton title="Category History">
          <p>
            One category over time: what was assigned each month, what was spent, and what was left
            at month end. These are the budget page&apos;s own figures for each month, not a
            re-derivation.
          </p>
          <p>
            The totals and the average cover the picker&apos;s complete months. The month in
            progress is drawn after them, marked <em>so far</em>.
          </p>
        </ReportInfoButton>
        <div className="flex-row">
          <select
            className="report-btn"
            value={categoryId}
            onChange={(e) => setCategoryId(e.target.value)}
            aria-label="Category"
          >
            <option value="">Pick a category…</option>
            <GroupedCategoryOptions groups={sections} />
          </select>
          <ReportRangeSelect />
        </div>
        <div style={{ marginLeft: 'auto' }}>
          <ReportExportButton
            reportId="category-history"
            getRows={() =>
              rows.map((m) => ({
                month: m.month,
                partial_month: m.partial_month,
                assigned: m.assigned,
                activity: m.activity,
                available: m.available,
              }))
            }
            captureRef={captureRef}
          />
        </div>
      </div>

      {!categoryId ? (
        <div className="reports-empty">
          <p>Pick a category to see its month-by-month history.</p>
        </div>
      ) : isLoading ? (
        <div className="report-loading">Loading...</div>
      ) : isError ? (
        <ReportErrorState error={error} onRetry={() => refetch()} />
      ) : data ? (
        <div ref={captureRef} className="report-capture">
          <MetricRow>
            <MetricCard label="Assigned" value={formatMoney(assigned)} sub={over} />
            <MetricCard label="Spent" value={formatMoney(spent)} sub={over} />
            <MetricCard
              label="Average spent"
              value={formatMoney(complete.length ? spent / complete.length : 0)}
              sub={`per month, over ${completeMonths(complete.length)}`}
            />
            <MetricCard label="Available now" value={availableNow} />
          </MetricRow>
          <div className="report-chart" style={{ height: chartHeight }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
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
                      formatter={formatMoney}
                    />
                  )}
                />
                <Legend />
                <Bar dataKey="Assigned" fill={COLOR_POSITIVE}>
                  {chartData.map((d) => (
                    <Cell key={d.iso} fillOpacity={d.partial ? RUNNING_MONTH_OPACITY : 1} />
                  ))}
                </Bar>
                <Bar dataKey="Spent" fill={COLOR_NEGATIVE}>
                  {chartData.map((d) => (
                    <Cell key={d.iso} fillOpacity={d.partial ? RUNNING_MONTH_OPACITY : 1} />
                  ))}
                </Bar>
                <Line
                  type="monotone"
                  dataKey="Available"
                  stroke={COLOR_NET}
                  dot={false}
                  strokeWidth={2}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <table className="report-table">
            <caption className="sr-only">{data.category_name} by month</caption>
            <thead>
              <tr>
                <th scope="col" style={{ textAlign: 'left' }}>
                  Month
                </th>
                <th scope="col" style={{ textAlign: 'right' }}>
                  Assigned
                </th>
                <th scope="col" style={{ textAlign: 'right' }}>
                  Activity
                </th>
                <th scope="col" style={{ textAlign: 'right' }}>
                  Available
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((m) => (
                <tr key={m.month}>
                  <td>{reportMonthLabel(m.month, m.partial_month, formatMonthShort)}</td>
                  <td style={{ textAlign: 'right' }}>{formatMoney(m.assigned)}</td>
                  <td style={{ textAlign: 'right' }}>{formatMoney(m.activity)}</td>
                  <td
                    style={{
                      textAlign: 'right',
                      color: (m.available ?? 0) < 0 ? 'var(--color-negative)' : undefined,
                    }}
                  >
                    {formatMoneyOrDash(m.available)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  )
}
