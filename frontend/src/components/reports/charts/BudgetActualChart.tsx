import { useRef, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { planSpentDrill, useReportScope, useReportStore } from '../../../stores/reportStore'
import { useBudgetActualReport } from '../../../api/reports'
import { useFormatters } from '../../../hooks/useFormatters'
import { useMoneyAxis } from '../../../hooks/useMoneyAxis'
import { ReportErrorState } from '../ReportErrorState'
import { COLOR_NEGATIVE, COLOR_NEUTRAL, COLOR_POSITIVE } from './chartColors'
import { DrillDownTable } from '../DrillDownTable'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { truncateLabel } from '../../../utils/truncateLabel'
import { ReportNotes } from '../ReportNotes'
import { NO_PLAN, varianceHeadline } from './budgetActualView'
import { planLabel } from './planLabel'

interface Props {
  budgetId: string
}

type SortMode = 'default' | 'overspent'

function BudgetActualTooltip({
  active,
  payload,
  label,
  chartData,
  formatMoney,
}: {
  active?: boolean
  payload?: { name: string; value: number }[]
  label?: string
  chartData: { name: string; group: string }[]
  formatMoney: (amount: number) => string
}) {
  if (!active || !payload?.length) return null
  const entry = chartData.find((d) => d.name === label)
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip__label">{label}</div>
      {entry?.group && (
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>
          {entry.group}
        </div>
      )}
      {payload.map((p) => (
        <div key={p.name} className="chart-tooltip__row">
          <span className="chart-tooltip__name">{p.name}</span>
          <span className="chart-tooltip__value">{formatMoney(p.value)}</span>
        </div>
      ))}
    </div>
  )
}

export function BudgetActualReport({ budgetId }: Props) {
  const { formatMoney } = useFormatters()
  const moneyAxis = useMoneyAxis()
  const { filters, setDrillDown } = useReportStore()
  const [showOverspent, setShowOverspent] = useState(false)
  const [sortBy, setSortBy] = useState<SortMode>('default')
  // Categories, tags and a saved filter, as the filter bar offers them here.
  const reportScope = useReportScope()
  const { data, isLoading, isError, error, refetch } = useBudgetActualReport(
    budgetId,
    filters.startDate,
    filters.endDate,
    reportScope
  )
  const captureRef = useRef<HTMLDivElement>(null)

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  const allCategories = data?.categories ?? []
  let categories = allCategories
  // `overspent` and `variance` are the server's verdict against the plan
  // floored at zero. Deciding them here from `spent > assigned` drew a drained
  // envelope (a negative assignment, nothing spent) as a red overrun.
  if (showOverspent) categories = categories.filter((c) => c.overspent)
  if (sortBy === 'overspent') {
    categories = [...categories].sort((a, b) => a.variance - b.variance)
  }

  const chartData = categories.slice(0, 20).map((c) => ({
    name: truncateLabel(c.category_name, 16),
    fullName: c.category_name,
    categoryId: c.category_id,
    group: c.category_group_name,
    // The served plan — assigned plus money moved in less money moved out,
    // floored. Drawing the raw assignment put a 2,000 bill paid from savings
    // beside a zero bar.
    Planned: c.plan,
    Spent: c.spent,
    overspent: c.overspent,
  }))

  function drillTo(categoryId: string, name: string) {
    setDrillDown(
      planSpentDrill(categoryId, name, { startDate: filters.startDate, endDate: filters.endDate })
    )
  }

  const barClick = (data: unknown) => {
    const d = data as {
      categoryId?: string
      fullName?: string
      payload?: { categoryId?: string; fullName?: string }
    }
    const id = d.categoryId ?? d.payload?.categoryId
    const name = d.fullName ?? d.payload?.fullName
    if (id && name) drillTo(id, name)
  }

  const headline = data ? varianceHeadline(data.total_variance, formatMoney) : null

  const tableRows = categories.map((c) => ({
    id: c.category_id,
    name: c.category_name,
    subName: c.category_group_name,
    amount: c.spent,
    pct: c.variance_pct,
    extra: planLabel(c, formatMoney),
  }))

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Budget vs Actual</h2>
        <ReportInfoButton title="Budget vs Actual">
          <p>
            Compares each category&apos;s <strong>plan</strong> — what you assigned, plus money
            moved into the envelope, less money moved out of it — with what you{' '}
            <strong>spent</strong> in the selected dates, net of refunds.
          </p>
          <p>
            <strong>Green bars</strong> = within plan. <strong>Red bars</strong> = over it by at
            least $1 and 1%. Moving money in — a transfer from savings, a deposit filed to it —
            raises the plan, and moving it out — a transfer to a brokerage, a loan payment — lowers
            it; neither is spending. Money leaving a Savings envelope is the exception: that is what
            its plan was for, so it counts as spent.
          </p>
          <p>
            Use the <em>Overspent only</em> filter to focus on problem categories, and{' '}
            <em>Sort by overspent</em> to rank the biggest overruns first.
          </p>
          <ReportScopeNote report="budget-actual" />
        </ReportInfoButton>
        <div className="flex-row ms-auto" style={{ flexWrap: 'wrap' }}>
          <label className="report-toggle">
            <input
              type="checkbox"
              checked={showOverspent}
              onChange={(e) => setShowOverspent(e.target.checked)}
            />
            Overspent only
          </label>
          <button
            className={`report-btn ${sortBy === 'overspent' ? 'report-btn--active' : ''}`}
            onClick={() => setSortBy((s) => (s === 'overspent' ? 'default' : 'overspent'))}
            type="button"
          >
            Sort by overspent
          </button>
          <ReportExportButton
            reportId="budget-actual"
            getRows={() =>
              categories.map((c) => ({
                category: c.category_name,
                group: c.category_group_name,
                assigned: c.assigned,
                moved_in: c.moved_in,
                moved_out: c.moved_out,
                planned: c.plan,
                spent: c.spent,
                variance: c.variance,
                variance_pct: c.variance_pct,
              }))
            }
            captureRef={captureRef}
            window={{ start: filters.startDate, end: filters.endDate }}
          />
        </div>
      </div>

      {/* A deleted saved filter drops its share of the scope; say so rather
          than let the report read as a quiet period. */}
      <ReportNotes report={data} toggleAvailable={false} />

      <div ref={captureRef} className="report-capture">
        {headline && data && (
          <MetricRow>
            <MetricCard label="Planned" value={formatMoney(data.total_plan)} />
            <MetricCard label="Spent" value={formatMoney(data.total_spent)} sub="net of refunds" />
            <MetricCard label={headline.label} value={headline.value} warning={headline.over} />
          </MetricRow>
        )}

        {chartData.length === 0 ? (
          <div className="reports-empty">No budget data for this period.</div>
        ) : (
          <>
            <ResponsiveContainer width="100%" height={Math.max(300, chartData.length * 36)}>
              <BarChart
                data={chartData}
                layout="vertical"
                margin={{ top: 4, right: 80, left: 4, bottom: 4 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="var(--border-color)"
                  horizontal={false}
                />
                <XAxis
                  type="number"
                  tickFormatter={moneyAxis.tickFormatter}
                  tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                  width={80}
                />
                <YAxis
                  type="category"
                  dataKey="name"
                  tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                  width={130}
                />
                <Tooltip
                  content={<BudgetActualTooltip chartData={chartData} formatMoney={formatMoney} />}
                  offset={16}
                  isAnimationActive={false}
                />
                <Legend />
                <Bar
                  dataKey="Planned"
                  fill={COLOR_NEUTRAL}
                  radius={[0, 2, 2, 0]}
                  barSize={10}
                  cursor="pointer"
                  onClick={barClick}
                />
                <Bar
                  dataKey="Spent"
                  fill={COLOR_POSITIVE}
                  barSize={10}
                  radius={[0, 2, 2, 0]}
                  cursor="pointer"
                  onClick={barClick}
                >
                  {chartData.map((entry, i) => (
                    <Cell key={i} fill={entry.overspent ? COLOR_NEGATIVE : COLOR_POSITIVE} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <DrillDownTable
              rows={tableRows}
              // The period's whole spend, which used to be handed over as the
              // rows' own total — so with "Overspent only" ticked the footer
              // was larger than the column above it.
              wider={{
                total: Number(data?.total_spent ?? 0),
                count: allCategories.length,
                label: 'categories',
              }}
              amountLabel="Spent"
              pctLabel="vs plan"
              extraLabel="Planned"
              pctAbsent={NO_PLAN}
              onRowClick={(row) => drillTo(row.id, row.name)}
            />
          </>
        )}
      </div>
    </div>
  )
}
