import { useMemo, useRef, useState } from 'react'
import {
  Bar, Cell, ComposedChart, CartesianGrid, Legend, Line,
  ResponsiveContainer, Tooltip, XAxis, YAxis, ReferenceLine,
} from 'recharts'
import { useReportStore, type GroupBy } from '../../../stores/reportStore'
import { useSpendingGroupedReport, usePayeeAnalysisReport } from '../../../api/reports'
import { useChartHeight } from '../../../hooks/useChartHeight'
import { useFormatters } from '../../../hooks/useFormatters'
import { DrillDownTable } from '../DrillDownTable'
import { MetricCard } from '../MetricCard'
import { ReportErrorState } from '../ReportErrorState'
import { CHART_COLORS, COLOR_NEGATIVE, chartColor } from './chartColors'
import { buildParetoItems, cumulativePercents, paretoAdherence, paretoInsight, shareOfTotal } from './paretoData'
import { ReportInfoButton, ReportScopeNote, SpendingClassNote } from '../ReportInfoButton'
import { LogScaleToggle, logAxisProps } from './logScale'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'

interface Props { budgetId: string }

const GROUP_LABELS: Record<GroupBy, string> = {
  category: 'Category',
  group: 'Category Group',
  payee: 'Payee',
}

const GROUP_PLURALS: Record<GroupBy, string> = {
  category: 'categories',
  group: 'category groups',
  payee: 'payees',
}

function ParetoTooltip({
  active,
  payload,
  label,
  chartData,
  formatMoney,
}: {
  active?: boolean
  payload?: { name: string; value: number }[]
  label?: string
  chartData: { name: string; fullName: string; group: string | null }[]
  formatMoney: (amount: number) => string
}) {
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

export function ParetoReport({ budgetId }: Props) {
  const chartHeight = useChartHeight(340)
  const { formatMoney } = useFormatters()
  const { filters, setDrillDown } = useReportStore()
  const groupBy = filters.groupBy
  const captureRef = useRef<HTMLDivElement>(null)
  const [includeSavings, setIncludeSavings] = useState(false)
  const [logScale, setLogScale] = useState(false)

  const catIds = filters.categoryIds.length > 0 ? filters.categoryIds : undefined
  const payeeIds = filters.payeeIds.length > 0 ? filters.payeeIds : undefined
  const acctIds = filters.accountIds.length > 0 ? filters.accountIds : undefined

  // Both queries always fetched — hooks must be unconditional
  // Only meaningful for category/group views, not the payee view
  const withSavings = includeSavings && groupBy !== 'payee'
  const spendingQ = useSpendingGroupedReport(budgetId, filters.startDate, filters.endDate, catIds, acctIds, withSavings, filters.viewId)
  const payeeQ = usePayeeAnalysisReport(budgetId, filters.startDate, filters.endDate, 25, payeeIds, acctIds)

  const spendingItems = useMemo(() => spendingQ.data?.groups ?? [], [spendingQ.data])
  const payeeItems = useMemo(() => payeeQ.data?.payees ?? [], [payeeQ.data])

  const groupColorMap = useMemo(() => {
    const map = new Map<string, string>()
    let idx = 0
    for (const item of spendingItems) {
      const key = item.parent_id ?? '__none__'
      if (!map.has(key)) map.set(key, chartColor(idx++))
    }
    return map
  }, [spendingItems])

  const { sorted, grandTotal } = useMemo(
    () => buildParetoItems(groupBy, spendingItems, payeeItems, spendingQ.data?.total),
    [groupBy, spendingItems, payeeItems, spendingQ.data],
  )

  // Group id → member category ids, for expanding a group drill client-side
  const groupMembers = useMemo(() => {
    const m = new Map<string, string[]>()
    for (const item of spendingItems) {
      const key = item.parent_id ?? '__none__'
      m.set(key, [...(m.get(key) ?? []), item.id])
    }
    return m
  }, [spendingItems])

  // All hooks above — safe to conditionally return now
  const activeQ = groupBy === 'payee' ? payeeQ : spendingQ
  if (activeQ.isLoading) return <div className="report-loading">Loading…</div>
  if (activeQ.isError) return <ReportErrorState error={activeQ.error} onRetry={() => activeQ.refetch()} />

  function drillTo(id: string, name: string) {
    const window = { startDate: filters.startDate, endDate: filters.endDate }
    if (groupBy === 'payee') {
      setDrillDown({
        kind: 'payee', label: name, scope: 'parent', direction: 'outflow',
        payeeIds: [id], ...window,
      })
    } else if (groupBy === 'group') {
      const memberIds = groupMembers.get(id) ?? []
      if (memberIds.length === 0) return
      setDrillDown({
        kind: 'category-group', label: name, scope: 'leaf', direction: 'outflow',
        categoryIds: memberIds, ...window,
      })
    } else {
      setDrillDown({
        kind: 'category', label: name, scope: 'leaf', direction: 'outflow',
        categoryIds: [id], ...window,
      })
    }
  }

  const top20 = sorted.slice(0, 20)
  const cumulativePcts = cumulativePercents(top20, grandTotal)
  const chartData = top20.map((item, i) => ({
    name: item.name.length > 14 ? item.name.slice(0, 12) + '…' : item.name,
    fullName: item.name,
    group: item.groupName,
    Amount: item.total,
    'Cumulative %': cumulativePcts[i],
    color: groupBy === 'group'
      ? chartColor(i)
      : (groupColorMap.get(item.groupKey ?? '__none__') ?? CHART_COLORS[0]),
  }))

  const { idx80, pct80coverage } = paretoInsight(cumulativePcts, sorted.length)
  const adherence = paretoAdherence(pct80coverage, sorted.length)

  const tableRows = sorted.map((item) => ({
    id: item.id,
    name: item.name,
    subName: item.groupName ?? '',
    amount: -item.total,
    pct: shareOfTotal(item.total, grandTotal),
  }))

  return (
    <div className="report-section">
      <div className="report-section__header">
        <h2 className="report-section__title">Pareto Analysis (80/20 Rule)</h2>
        <ReportInfoButton title="Pareto Analysis">
          <p>The <strong>80/20 rule</strong>: roughly 80% of your spending comes from 20% of your categories. This chart shows where spending concentrates.</p>
          <p><strong>Bars</strong> show individual amounts (colored by category group). The <strong>orange line</strong> is the running cumulative percentage. The <strong>red dashed line</strong> marks 80%.</p>
          <p>Switch the <strong>Group by</strong> filter in the toolbar to see the pattern at the category group, category, or payee level.</p>
          <p>Click a bar or a table row to see the transactions behind it.</p>
          <ReportScopeNote scope="on-budget-filterable" />
          <SpendingClassNote />
        </ReportInfoButton>
        {groupBy !== 'payee' && (
          <label className="report-toggle">
            <input
              type="checkbox"
              checked={includeSavings}
              onChange={(e) => setIncludeSavings(e.target.checked)}
            />
            <span title="Money moved into savings or used to pay down a tracked debt isn't spending, so it's left out by default. Tick to add it back.">
              Include savings &amp; debt payments
            </span>
          </label>
        )}
        <div className="flex-row ms-auto">
          <LogScaleToggle enabled={logScale} onToggle={() => setLogScale((v) => !v)} />
          <ReportExportButton
            reportId="pareto"
            getRows={() =>
              sorted.map((item) => ({
                name: item.name,
                group: item.groupName ?? '',
                total: item.total,
                pct: grandTotal > 0 ? (item.total / grandTotal) * 100 : 0,
              }))
            }
            captureRef={captureRef}
            window={{ start: filters.startDate, end: filters.endDate }}
          />
        </div>
      </div>
      <p className="report-section__subtitle">
        Which {GROUP_PLURALS[groupBy]} account for 80% of your spending?
      </p>

      <div ref={captureRef} className="report-capture">
      {grandTotal > 0 && (
        <div className="report-metrics">
          <MetricCard label="Total Spending" value={formatMoney(grandTotal)} />
          {idx80 >= 0 && (
            <MetricCard
              label="80% of Spend"
              value={`${idx80 + 1} ${idx80 === 0 ? GROUP_LABELS[groupBy].toLowerCase() : GROUP_PLURALS[groupBy]}`}
              sub={adherence ? adherence.message : `${pct80coverage}% of all ${GROUP_PLURALS[groupBy]}`}
              warning={adherence ? !adherence.adherent : false}
            />
          )}
        </div>
      )}

      {chartData.length === 0 ? (
        <div className="reports-empty">No spending data for this period.</div>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={chartHeight}>
            <ComposedChart data={chartData} margin={{ top: 8, right: 50, left: 0, bottom: 60 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
              <XAxis dataKey="name" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} angle={-40} textAnchor="end" interval={0} height={70} />
              <YAxis yAxisId="left" tickFormatter={(v) => formatMoney(v)} tick={{ fontSize: 11, fill: 'var(--text-muted)' }} width={90} {...logAxisProps(logScale)} />
              <YAxis yAxisId="right" orientation="right" domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 11, fill: 'var(--text-muted)' }} width={50} />
              <Tooltip content={<ParetoTooltip chartData={chartData} formatMoney={formatMoney} />} offset={16} isAnimationActive={false} />
              <Legend verticalAlign="top" />
              <ReferenceLine yAxisId="right" y={80} stroke={COLOR_NEGATIVE} strokeDasharray="6 3" label={{ value: '80%', position: 'right', fontSize: 11 }} />
              <Bar
                yAxisId="left"
                dataKey="Amount"
                radius={[2, 2, 0, 0]}
                cursor="pointer"
                onClick={(data) => {
                  const d = data as { fullName?: string; payload?: { fullName?: string } }
                  const full = d.fullName ?? d.payload?.fullName
                  const item = sorted.find((s) => s.name === full)
                  if (item) drillTo(item.id, item.name)
                }}
              >
                {chartData.map((entry, i) => (
                  <Cell key={i} fill={entry.color} fillOpacity={0.85} />
                ))}
              </Bar>
              <Line yAxisId="right" type="monotone" dataKey="Cumulative %" stroke={CHART_COLORS[1]} strokeWidth={2} dot={{ r: 3 }} />
            </ComposedChart>
          </ResponsiveContainer>
          <DrillDownTable
            rows={tableRows}
            total={grandTotal}
            onRowClick={(row) => drillTo(row.id, row.name)}
          />
        </>
      )}
      </div>
    </div>
  )
}
