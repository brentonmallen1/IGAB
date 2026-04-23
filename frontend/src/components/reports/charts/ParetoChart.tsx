import { useMemo } from 'react'
import {
  Bar, Cell, ComposedChart, CartesianGrid, Line,
  ResponsiveContainer, Tooltip, XAxis, YAxis, ReferenceLine,
} from 'recharts'
import { useReportStore, type GroupBy } from '../../../stores/reportStore'
import { useSpendingGroupedReport, usePayeeAnalysisReport } from '../../../api/reports'
import { formatMoney } from '../../../utils/money'
import { DrillDownTable } from '../DrillDownTable'
import { MetricCard } from '../MetricCard'
import { CHART_COLORS } from './chartColors'
import { ReportInfoButton } from '../ReportInfoButton'

interface Props { budgetId: string }

const GROUP_LABELS: Record<GroupBy, string> = {
  category: 'Category',
  group: 'Category Group',
  payee: 'Payee',
}

export function ParetoReport({ budgetId }: Props) {
  const { filters } = useReportStore()
  const groupBy = filters.groupBy

  const catIds = filters.categoryIds.length > 0 ? filters.categoryIds : undefined
  const payeeIds = filters.payeeIds.length > 0 ? filters.payeeIds : undefined
  const acctIds = filters.accountIds.length > 0 ? filters.accountIds : undefined

  // Both queries always fetched — hooks must be unconditional
  const spendingQ = useSpendingGroupedReport(budgetId, filters.startDate, filters.endDate, catIds, acctIds)
  const payeeQ = usePayeeAnalysisReport(budgetId, filters.startDate, filters.endDate, 25, payeeIds, acctIds)

  const spendingItems = spendingQ.data?.groups ?? []
  const payeeItems = payeeQ.data?.payees ?? []

  const groupColorMap = useMemo(() => {
    const map = new Map<string, string>()
    let idx = 0
    for (const item of spendingItems) {
      const key = item.parent_id ?? '__none__'
      if (!map.has(key)) map.set(key, CHART_COLORS[idx++ % CHART_COLORS.length])
    }
    return map
  }, [spendingItems])

  const { sorted, grandTotal } = useMemo(() => {
    if (groupBy === 'payee') {
      const items = [...payeeItems].sort((a, b) => Number(b.total) - Number(a.total))
      const total = items.reduce((s, p) => s + Number(p.total), 0)
      return {
        sorted: items.map((p) => ({
          id: p.payee_id, name: p.payee_name, total: Number(p.total),
          groupKey: null as string | null, groupName: null as string | null,
        })),
        grandTotal: total,
      }
    }
    if (groupBy === 'group') {
      const map = new Map<string, { id: string; name: string; total: number }>()
      for (const item of spendingItems) {
        const gid = item.parent_id ?? '__none__'
        const ex = map.get(gid)
        if (ex) { ex.total += Number(item.total) }
        else map.set(gid, { id: gid, name: item.parent_name ?? 'Uncategorized', total: Number(item.total) })
      }
      const items = [...map.values()].sort((a, b) => b.total - a.total)
      const total = items.reduce((s, i) => s + i.total, 0)
      return {
        sorted: items.map((i) => ({ ...i, groupKey: i.id, groupName: null as string | null })),
        grandTotal: total,
      }
    }
    const items = [...spendingItems].sort((a, b) => Number(b.total) - Number(a.total))
    const total = Number(spendingQ.data?.total ?? 0)
    return {
      sorted: items.map((i) => ({
        id: i.id, name: i.name, total: Number(i.total),
        groupKey: i.parent_id, groupName: i.parent_name,
      })),
      grandTotal: total,
    }
  }, [groupBy, spendingItems, payeeItems, spendingQ.data])

  // All hooks above — safe to conditionally return now
  const isLoading = groupBy === 'payee' ? payeeQ.isLoading : spendingQ.isLoading
  if (isLoading) return <div className="report-loading">Loading…</div>

  let running = 0
  const chartData = sorted.slice(0, 20).map((item, i) => {
    running += item.total
    return {
      name: item.name.length > 14 ? item.name.slice(0, 12) + '…' : item.name,
      fullName: item.name,
      group: item.groupName,
      Amount: item.total,
      'Cumulative %': grandTotal > 0 ? (running / grandTotal) * 100 : 0,
      color: groupBy === 'group'
        ? CHART_COLORS[i % CHART_COLORS.length]
        : (groupColorMap.get(item.groupKey ?? '__none__') ?? CHART_COLORS[0]),
    }
  })

  const idx80 = chartData.findIndex((d) => d['Cumulative %'] >= 80)
  const pct80coverage = idx80 >= 0 ? ((idx80 + 1) / sorted.length * 100).toFixed(0) : null

  const tableRows = sorted.map((item) => ({
    id: item.id,
    name: item.name,
    subName: item.groupName ?? '',
    amount: -item.total,
    pct: grandTotal > 0 ? (item.total / grandTotal) * 100 : 0,
  }))

  const CustomTooltip = ({ active, payload, label }: { active?: boolean; payload?: { name: string; value: number }[]; label?: string }) => {
    if (!active || !payload?.length) return null
    const entry = chartData.find((d) => d.name === label)
    return (
      <div className="chart-tooltip">
        <div className="chart-tooltip__label">{entry?.fullName ?? label}</div>
        {entry?.group && <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>{entry.group}</div>}
        {payload.map((p) => (
          <div key={p.name} className="chart-tooltip__row">
            <span className="chart-tooltip__name">{p.name}</span>
            <span className="chart-tooltip__value">
              {p.name === 'Cumulative %' ? `${p.value.toFixed(1)}%` : formatMoney(p.value)}
            </span>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="report-section">
      <div className="report-section__controls">
        <h2 className="report-section__title">Pareto Analysis (80/20 Rule)</h2>
        <ReportInfoButton title="Pareto Analysis">
          <p>The <strong>80/20 rule</strong>: roughly 80% of your spending comes from 20% of your categories. This chart shows where spending concentrates.</p>
          <p><strong>Bars</strong> show individual amounts (colored by category group). The <strong>orange line</strong> is the running cumulative percentage. The <strong>red dashed line</strong> marks 80%.</p>
          <p>Switch the <strong>Group by</strong> filter in the toolbar to see the pattern at the category group, category, or payee level.</p>
        </ReportInfoButton>
      </div>
      <p className="report-section__subtitle">
        Which {GROUP_LABELS[groupBy].toLowerCase()}s account for 80% of your spending?
      </p>

      {grandTotal > 0 && (
        <div className="report-metrics">
          <MetricCard label="Total Spending" value={formatMoney(grandTotal)} />
          {idx80 >= 0 && (
            <MetricCard
              label="80% of Spend"
              value={`${idx80 + 1} ${GROUP_LABELS[groupBy].toLowerCase()}s`}
              sub={pct80coverage ? `${pct80coverage}% of all ${GROUP_LABELS[groupBy].toLowerCase()}s` : undefined}
            />
          )}
        </div>
      )}

      {chartData.length === 0 ? (
        <div className="reports-empty">No spending data for this period.</div>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={340}>
            <ComposedChart data={chartData} margin={{ top: 8, right: 50, left: 0, bottom: 60 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} angle={-40} textAnchor="end" interval={0} height={70} />
              <YAxis yAxisId="left" tickFormatter={(v) => formatMoney(v)} tick={{ fontSize: 11 }} width={90} />
              <YAxis yAxisId="right" orientation="right" domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 11 }} width={50} />
              <Tooltip content={<CustomTooltip />} offset={16} isAnimationActive={false} />
              <ReferenceLine yAxisId="right" y={80} stroke="#e15759" strokeDasharray="6 3" label={{ value: '80%', position: 'right', fontSize: 11 }} />
              <Bar yAxisId="left" dataKey="Amount" radius={[2, 2, 0, 0]}>
                {chartData.map((entry, i) => (
                  <Cell key={i} fill={entry.color} fillOpacity={0.85} />
                ))}
              </Bar>
              <Line yAxisId="right" type="monotone" dataKey="Cumulative %" stroke="#f28e2b" strokeWidth={2} dot={{ r: 3 }} />
            </ComposedChart>
          </ResponsiveContainer>
          <DrillDownTable rows={tableRows} total={grandTotal} />
        </>
      )}
    </div>
  )
}
