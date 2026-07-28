import { useRef, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { useReportStore } from '../../../stores/reportStore'
import { useBudgetActualReport } from '../../../api/reports'
import { useFormatters } from '../../../hooks/useFormatters'
import { DrillDownTable } from '../DrillDownTable'
import { MetricCard } from '../MetricCard'
import { ReportInfoButton } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'

interface Props { budgetId: string }

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
      {entry?.group && <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>{entry.group}</div>}
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
  const { filters, setDrillDown } = useReportStore()
  const [showOverspent, setShowOverspent] = useState(false)
  const [sortBy, setSortBy] = useState<SortMode>('default')
  const catIds = filters.categoryIds.length > 0 ? filters.categoryIds : undefined
  const { data, isLoading } = useBudgetActualReport(budgetId, filters.startDate, filters.endDate, catIds)
  const captureRef = useRef<HTMLDivElement>(null)

  if (isLoading) return <div className="report-loading">Loading…</div>

  let categories = data?.categories ?? []
  if (showOverspent) categories = categories.filter((c) => Number(c.spent) > Number(c.assigned))
  if (sortBy === 'overspent') {
    categories = [...categories].sort(
      (a, b) => (Number(b.spent) - Number(b.assigned)) - (Number(a.spent) - Number(a.assigned))
    )
  }

  const chartData = categories.slice(0, 20).map((c) => ({
    name: c.category_name.length > 16 ? c.category_name.slice(0, 14) + '…' : c.category_name,
    fullName: c.category_name,
    categoryId: c.category_id,
    group: c.category_group_name,
    Assigned: Number(c.assigned),
    Spent: Number(c.spent),
    overspent: Number(c.spent) > Number(c.assigned),
  }))

  function drillTo(categoryId: string, name: string) {
    setDrillDown({
      kind: 'category', label: name, scope: 'leaf', direction: 'outflow',
      categoryIds: [categoryId], startDate: filters.startDate, endDate: filters.endDate,
    })
  }

  const barClick = (data: unknown) => {
    const d = data as { categoryId?: string; fullName?: string; payload?: { categoryId?: string; fullName?: string } }
    const id = d.categoryId ?? d.payload?.categoryId
    const name = d.fullName ?? d.payload?.fullName
    if (id && name) drillTo(id, name)
  }

  const tableRows = categories.map((c) => ({
    id: c.category_id,
    name: c.category_name,
    subName: c.category_group_name,
    amount: -Number(c.spent),
    pct: Number(c.variance_pct),
    extra: `Assigned: ${formatMoney(Number(c.assigned))}`,
  }))

  return (
    <div className="report-section">
      <div className="report-section__header">
        <h2 className="report-section__title">Budget vs Actual</h2>
        <ReportInfoButton title="Budget vs Actual">
          <p>Compares how much you <strong>assigned</strong> to each category versus how much you actually <strong>spent</strong> in the selected date range.</p>
          <p><strong>Green bars</strong> = under budget. <strong>Red bars</strong> = over budget (spent more than assigned).</p>
          <p>Use the <em>Overspent only</em> filter to focus on problem categories, and <em>Sort by overspent</em> to rank the biggest overruns first.</p>
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
            onClick={() => setSortBy((s) => s === 'overspent' ? 'default' : 'overspent')}
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
                assigned: Number(c.assigned),
                spent: Number(c.spent),
                variance: Number(c.assigned) - Number(c.spent),
                variance_pct: Number(c.variance_pct),
              }))
            }
            captureRef={captureRef}
            window={{ start: filters.startDate, end: filters.endDate }}
          />
        </div>
      </div>

      <div ref={captureRef} className="report-capture">
      {data && (
        <div className="report-metrics">
          <MetricCard label="Total Assigned" value={formatMoney(Number(data.total_assigned))} />
          <MetricCard label="Total Spent" value={formatMoney(Number(data.total_spent))} />
          <MetricCard
            label="Variance"
            value={formatMoney(Number(data.total_assigned) - Number(data.total_spent))}
          />
        </div>
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
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" horizontal={false} />
              <XAxis type="number" tickFormatter={(v) => formatMoney(v)} tick={{ fontSize: 11 }} width={80} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={130} />
              <Tooltip content={<BudgetActualTooltip chartData={chartData} formatMoney={formatMoney} />} offset={16} isAnimationActive={false} />
              <Bar dataKey="Assigned" fill="#4e79a7" radius={[0, 2, 2, 0]} barSize={10} cursor="pointer" onClick={barClick} />
              <Bar dataKey="Spent" barSize={10} radius={[0, 2, 2, 0]} cursor="pointer" onClick={barClick}>
                {chartData.map((entry, i) => (
                  <Cell key={i} fill={entry.overspent ? '#e15759' : '#59a14f'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <DrillDownTable
            rows={tableRows}
            total={Number(data?.total_spent ?? 0)}
            amountLabel="Spent"
            onRowClick={(row) => drillTo(row.id, row.name)}
          />
        </>
      )}
      </div>
    </div>
  )
}
