import { useMemo, useRef } from 'react'
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
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
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ChartTooltip } from './ChartTooltip'
import { averagedOver, completeMonths } from './averagedOver'
import { ChartLegend } from './ChartLegend'
import { CHART_COLORS, COLOR_NEGATIVE, COLOR_NET, COLOR_NEUTRAL } from './chartColors'
import { historySpentColor } from './categoryHistoryView'
import { useReportMonths, useReportStore } from '../../../stores/reportStore'
import { useMoneyAxis } from '../../../hooks/useMoneyAxis'
import {
  completeMonthRows,
  monthRange,
  reportMonthLabel,
  RUNNING_MONTH_OPACITY,
} from '../../../utils/reportMonths'
import { fromCents, sumToCents } from '../../../utils/money'

interface Props {
  budgetId: string
}

/** One category, month by month: assigned, spent, and what was left — the
 *  budget page's own assigned, activity and available, and the plan
 *  reports' Spent. */
export function CategoryHistoryReport({ budgetId }: Props) {
  const { formatMoney, formatMoneyOrDash, formatMonthShort } = useFormatters()
  const moneyAxis = useMoneyAxis()
  const chartHeight = useChartHeight(320)
  const storedId = useReportStore((s) => s.historyCategoryId)
  const setCategoryId = useReportStore((s) => s.setHistoryCategoryId)
  const months = useReportMonths()
  const captureRef = useRef<HTMLDivElement>(null)
  const { data: categories = [] } = useCategories(budgetId)
  const { data: groups = [] } = useCategoryGroups(budgetId)
  const pickable = useMemo(() => categories.filter((c) => c.is_categorizable), [categories])
  const sections = useMemo(() => groupedCategorySections(pickable, groups), [pickable, groups])
  // A remembered pick that no longer names a category you can pick (deleted,
  // archived, another budget's) asks again rather than asking the server.
  const categoryId = pickable.some((c) => c.id === storedId) ? storedId : ''
  const { data, isLoading, isError, error, refetch } = useCategoryHistoryReport(
    budgetId,
    categoryId || null,
    months
  )

  const chartData = useMemo(
    () =>
      (data?.months ?? []).map((m) => ({
        month: reportMonthLabel(m.month, m.partial_month, formatMonthShort),
        Assigned: m.assigned,
        Spent: m.spent,
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
  // from the 1st while its spending arrives over the month, and adding it in
  // read every category low at the start of a month. The average is served,
  // over the same complete months.
  const complete = completeMonthRows(rows)
  const spent = fromCents(sumToCents(complete.map((m) => m.spent)))
  const assigned = fromCents(sumToCents(complete.map((m) => m.assigned)))
  const covered = monthRange(complete[0]?.month, complete.at(-1)?.month, formatMonthShort)
  const over = covered ?? `over ${completeMonths(complete.length)}`
  const anyMovedIn = rows.some((m) => m.moved_in !== 0)
  const anyMovedOut = rows.some((m) => m.moved_out !== 0)

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Category History</h2>
        <ReportInfoButton title="Category History">
          <p>
            One category over time: what was assigned each month, what was spent, and what was left
            at month end. Assigned, Activity and Available are the budget page&apos;s own figures.
          </p>
          <p>
            <strong>Spent</strong> is net of refunds and leaves out money moved into or out of the
            envelope — a transfer from savings, or to a brokerage, is not spending, though Activity
            nets it. It is the figure the plan reports count. A Spent bar turns red in a month the
            envelope ended overspent.
          </p>
          <p>
            The totals and the average cover the picker&apos;s complete months. The month in
            progress is drawn after them, marked <em>so far</em>.
          </p>
          <ReportScopeNote report="category-history" />
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
                moved_in: m.moved_in,
                moved_out: m.moved_out,
                spent: m.spent,
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
            <MetricCard label="Spent (net of refunds)" value={formatMoney(spent)} sub={over} />
            <MetricCard
              label="Average spent"
              value={data.months_averaged > 0 ? formatMoney(data.average_spent) : '—'}
              sub={averagedOver('per month', data.months_averaged)}
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
                <Bar dataKey="Assigned" fill={COLOR_NEUTRAL}>
                  {rows.map((m) => (
                    <Cell key={m.month} fillOpacity={m.partial_month ? RUNNING_MONTH_OPACITY : 1} />
                  ))}
                </Bar>
                <Bar dataKey="Spent" fill={CHART_COLORS[0]}>
                  {rows.map((m) => (
                    <Cell
                      key={m.month}
                      fill={historySpentColor(m.available)}
                      fillOpacity={m.partial_month ? RUNNING_MONTH_OPACITY : 1}
                    />
                  ))}
                </Bar>
                <Line
                  type="linear"
                  dataKey="Available"
                  stroke={COLOR_NET}
                  dot={false}
                  strokeWidth={2}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          {/* Not recharts' legend: it keys Spent by the series fill, and a
              Spent bar takes its colour from its month's state. */}
          <ChartLegend
            series={[
              { id: 'assigned', name: 'Assigned', color: COLOR_NEUTRAL },
              { id: 'spent', name: 'Spent', color: CHART_COLORS[0] },
              { id: 'overspent', name: 'Spent, envelope overspent', color: COLOR_NEGATIVE },
              { id: 'available', name: 'Available', color: COLOR_NET },
            ]}
            active={null}
            onHover={() => {}}
          />
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
                {anyMovedIn && (
                  <th scope="col" style={{ textAlign: 'right' }}>
                    Moved in
                  </th>
                )}
                {anyMovedOut && (
                  <th scope="col" style={{ textAlign: 'right' }}>
                    Moved out
                  </th>
                )}
                <th scope="col" style={{ textAlign: 'right' }}>
                  Spent
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
                  {anyMovedIn && <td style={{ textAlign: 'right' }}>{formatMoney(m.moved_in)}</td>}
                  {anyMovedOut && (
                    <td style={{ textAlign: 'right' }}>{formatMoney(m.moved_out)}</td>
                  )}
                  <td style={{ textAlign: 'right' }}>{formatMoney(m.spent)}</td>
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
