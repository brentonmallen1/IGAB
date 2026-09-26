import { useMemo, useRef, useState } from 'react'
import {
  Bar,
  Cell,
  ComposedChart,
  CartesianGrid,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  ReferenceLine,
} from 'recharts'
import { useReportStore, type GroupBy } from '../../../stores/reportStore'
import { useSpendingGroupedReport, usePayeeAnalysisReport } from '../../../api/reports'
import { useChartHeight } from '../../../hooks/useChartHeight'
import { useFormatters } from '../../../hooks/useFormatters'
import { useMoneyAxis } from '../../../hooks/useMoneyAxis'
import { DrillDownTable } from '../DrillDownTable'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { ReportErrorState } from '../ReportErrorState'
import { CHART_COLORS, COLOR_NEGATIVE, chartColor } from './chartColors'
import { buildParetoItems, paretoSummary, type ParetoItem } from './paretoData'
import { shareOfTotal } from '../drillDownTotals'
import { ReportInfoButton, ReportScopeNote, SpendingClassNote } from '../ReportInfoButton'
import { ReportNotes, IncludeSavingsToggle, emptySpendingMessage } from '../ReportNotes'
import { LogScaleToggle, logAxisProps } from './logScale'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { useReportScope } from '../../../stores/reportStore'
import { categoryTarget } from '../drillScope'
import { truncateLabel } from '../../../utils/truncateLabel'
import { PAYEE_RANKED } from './reportControls'

interface Props {
  budgetId: string
}

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
      {entry?.group && (
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>
          {entry.group}
        </div>
      )}
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
  const moneyAxis = useMoneyAxis()
  const { filters, setDrillDown } = useReportStore()
  const groupBy = filters.groupBy
  const captureRef = useRef<HTMLDivElement>(null)
  const [includeSavings, setIncludeSavings] = useState(false)
  const [logScale, setLogScale] = useState(false)

  const reportScope = useReportScope()
  const payeeIds = filters.payeeIds.length > 0 ? filters.payeeIds : undefined
  const acctIds = filters.accountIds.length > 0 ? filters.accountIds : undefined

  // Both queries always fetched — hooks must be unconditional
  // Only meaningful for category/group views, not the payee view
  const withSavings = includeSavings && groupBy !== 'payee'
  const spendingQ = useSpendingGroupedReport(
    budgetId,
    filters.startDate,
    filters.endDate,
    reportScope,
    acctIds,
    withSavings,
    filters.viewId
  )
  const payeeQ = usePayeeAnalysisReport(
    budgetId,
    filters.startDate,
    filters.endDate,
    PAYEE_RANKED,
    payeeIds,
    acctIds
  )

  const spendingItems = useMemo(() => spendingQ.data?.groups ?? [], [spendingQ.data])

  const groupColorMap = useMemo(() => {
    const map = new Map<string, string>()
    let idx = 0
    for (const item of spendingItems) {
      const key = item.parent_id ?? '__none__'
      if (!map.has(key)) map.set(key, chartColor(idx++))
    }
    return map
  }, [spendingItems])

  const { sorted, grandTotal, universeCount, itemsTo80 } = useMemo(
    () => buildParetoItems(groupBy, spendingItems, spendingQ.data?.total, payeeQ.data),
    [groupBy, spendingItems, spendingQ.data, payeeQ.data]
  )

  // All hooks above — safe to conditionally return now
  const activeQ = groupBy === 'payee' ? payeeQ : spendingQ
  if (activeQ.isLoading) return <div className="report-loading">Loading…</div>
  if (activeQ.isError)
    return <ReportErrorState error={activeQ.error} onRetry={() => activeQ.refetch()} />

  /** The rows behind a bar: every row of the classes the active report
   *  counted (served), whichever way it went — spending is net of refunds.
   *  Payee mode carries no category scope: its report takes none, and the
   *  filter bar dims it there, so a drill that sent one listed less than the
   *  bar. */
  function drillTo(item: ParetoItem) {
    const window = { startDate: filters.startDate, endDate: filters.endDate }
    if (groupBy === 'payee') {
      if (!payeeQ.data) return
      setDrillDown({
        kind: 'payee',
        label: item.name,
        scope: 'leaf',
        payeeIds: [item.id],
        activityClasses: payeeQ.data.counted_classes,
        ...window,
      })
      return
    }
    if (!spendingQ.data || item.members.length === 0) return
    setDrillDown({
      kind: groupBy === 'group' ? 'category-group' : 'category',
      label: item.name,
      scope: 'leaf',
      ...categoryTarget(item.members),
      activityClasses: spendingQ.data.counted_classes,
      ...window,
    })
  }

  // `universeCount`, not `sorted.length`: in payee mode the server ranks the
  // top 25, and "% of all payees" measured against the cap was the cap
  // restated as a fact about the period.
  const { drawn, idx80, coverage } = paretoSummary(sorted, grandTotal, universeCount, itemsTo80)
  const chartData = drawn.map(({ item, cumulativePct }, i) => ({
    name: truncateLabel(item.name, 14),
    fullName: item.name,
    group: item.groupName,
    Amount: item.total,
    'Cumulative %': cumulativePct,
    color:
      groupBy === 'group'
        ? chartColor(i)
        : (groupColorMap.get(item.groupKey ?? '__none__') ?? CHART_COLORS[0]),
  }))

  const rankedIsEverything = universeCount === sorted.length

  const tableRows = sorted.map((item) => ({
    id: item.id,
    name: item.name,
    subName: item.groupName ?? '',
    amount: item.total,
    // No share to state against a total that is not positive, so no column.
    pct: shareOfTotal(item.total, grandTotal) ?? undefined,
  }))

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Pareto Analysis (80/20 Rule)</h2>
        <ReportInfoButton title="Pareto Analysis">
          <p>
            How few of your largest {GROUP_PLURALS[groupBy]} make up most of your spending. The card
            counts how many it takes to reach 80% of the period&apos;s total.
          </p>
          <p>
            <strong>Bars</strong> are each one&apos;s spending, largest first; in category mode they
            are shaded by group. The <strong>line</strong> is the running share of the total, and
            the <strong>dashed line</strong> marks 80%.
          </p>
          <p>
            Switch <strong>Group by</strong> in the toolbar to rank category groups, categories or
            payees. Payee mode ranks every payee and ignores the category, tag, saved-filter and
            view pickers, which dim; the other modes ignore the payee picker.
          </p>
          <p>Click a bar or a table row to see the transactions behind it.</p>
          <ReportScopeNote report="pareto" />
          <SpendingClassNote />
        </ReportInfoButton>
        {groupBy !== 'payee' && (
          <IncludeSavingsToggle checked={includeSavings} onChange={setIncludeSavings} />
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
                pct: shareOfTotal(item.total, grandTotal),
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
      {/* Payee mode draws from payee analysis, which no view filters. */}
      {groupBy !== 'payee' && (
        <ReportNotes report={spendingQ.data} toggleAvailable={!includeSavings} />
      )}

      <div ref={captureRef} className="report-capture">
        {grandTotal > 0 && (
          <MetricRow>
            <MetricCard label="Total Spending" value={formatMoney(grandTotal)} />
            {idx80 >= 0 && (
              <MetricCard
                label="80% of Spend"
                value={`${idx80 + 1} ${idx80 === 0 ? GROUP_LABELS[groupBy].toLowerCase() : GROUP_PLURALS[groupBy]}`}
                sub={
                  coverage === null
                    ? undefined
                    : `${coverage.toFixed(0)}% of ${rankedIsEverything ? 'all' : 'the'} ${GROUP_PLURALS[groupBy]}`
                }
              />
            )}
          </MetricRow>
        )}

        {chartData.length === 0 ? (
          <div className="reports-empty">
            {emptySpendingMessage(groupBy === 'payee' ? 0 : spendingQ.data?.view_hidden_categories)}
          </div>
        ) : (
          <>
            <ResponsiveContainer width="100%" height={chartHeight}>
              <ComposedChart data={chartData} margin={{ top: 8, right: 50, left: 0, bottom: 60 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                  angle={-40}
                  textAnchor="end"
                  interval={0}
                  height={70}
                />
                <YAxis
                  yAxisId="left"
                  tickFormatter={moneyAxis.tickFormatter}
                  tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                  width={moneyAxis.width}
                  {...logAxisProps(logScale)}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  domain={[0, 100]}
                  tickFormatter={(v) => `${v}%`}
                  tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                  width={50}
                />
                <Tooltip
                  content={<ParetoTooltip chartData={chartData} formatMoney={formatMoney} />}
                  offset={16}
                  isAnimationActive={false}
                />
                <Legend verticalAlign="top" />
                <ReferenceLine
                  yAxisId="right"
                  y={80}
                  stroke={COLOR_NEGATIVE}
                  strokeDasharray="6 3"
                  label={{ value: '80%', position: 'right', fontSize: 11 }}
                />
                <Bar
                  yAxisId="left"
                  dataKey="Amount"
                  radius={[2, 2, 0, 0]}
                  cursor="pointer"
                  onClick={(data) => {
                    const d = data as { fullName?: string; payload?: { fullName?: string } }
                    const full = d.fullName ?? d.payload?.fullName
                    const item = sorted.find((s) => s.name === full)
                    if (item) drillTo(item)
                  }}
                >
                  {chartData.map((entry, i) => (
                    <Cell key={i} fill={entry.color} fillOpacity={0.85} />
                  ))}
                </Bar>
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="Cumulative %"
                  stroke={CHART_COLORS[1]}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                />
              </ComposedChart>
            </ResponsiveContainer>
            <DrillDownTable
              rows={tableRows}
              wider={{ total: grandTotal, count: universeCount, label: GROUP_PLURALS[groupBy] }}
              pctIsShare
              amountLabel="Spent"
              onRowClick={(row) => {
                const item = sorted.find((s) => s.id === row.id)
                if (item) drillTo(item)
              }}
            />
          </>
        )}
      </div>
    </div>
  )
}
