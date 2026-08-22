import { useState, useMemo, useRef } from 'react'
import { ChevronRight } from 'lucide-react'
import { useReportStore } from '../../../stores/reportStore'
import { useCashFlowReport } from '../../../api/reports'
import { usePayees } from '../../../api/payees'
import { useChartHeight } from '../../../hooks/useChartHeight'
import { useFormatters } from '../../../hooks/useFormatters'
import { ReportErrorState } from '../ReportErrorState'
import { previousWindow } from '../../../utils/dateWindow'
import { MetricCard } from '../MetricCard'
import { CHART_COLORS, COLOR_NEGATIVE, COLOR_POSITIVE } from './chartColors'
import { Sankey, Tooltip, ResponsiveContainer } from 'recharts'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import type { CategoryPayee } from '../../../types'
import {
  buildSankeyView,
  deltaColor,
  extractPrevTotals,
  formatDelta,
  type SankeyViewNode,
} from './sankeyView'
import './CashFlowSankey.css'

interface Props { budgetId: string }

const NODE_COLORS: Record<string, string> = {
  income: COLOR_POSITIVE,
  category_group: CHART_COLORS[1],
  category: CHART_COLORS[3],
  payee: COLOR_NEGATIVE,
}

type NodeData = SankeyViewNode

function SankeyNodeRect(props: {
  x?: number; y?: number; width?: number; height?: number
  payload?: NodeData & { value?: number }
}) {
  const { formatMoney } = useFormatters()
  const { x = 0, y = 0, width = 0, height = 0, payload } = props
  if (!payload) return null
  const isLeft = payload.type === 'income'
  const color = NODE_COLORS[payload.type] ?? 'var(--text-muted)'
  const value = payload.value ?? 0
  const hasDelta = payload.prev !== undefined
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} fill={color} />
      <text
        x={isLeft ? x + width + 6 : x - 6}
        y={y + height / 2 - (hasDelta ? 6 : 0)}
        textAnchor={isLeft ? 'start' : 'end'}
        dominantBaseline="middle"
        fontSize={12}
        fill="var(--text-primary)"
        fontWeight={500}
      >
        {payload.name.length > 24 ? payload.name.slice(0, 22) + '…' : payload.name}
      </text>
      {hasDelta && (
        <text
          x={isLeft ? x + width + 6 : x - 6}
          y={y + height / 2 + 8}
          textAnchor={isLeft ? 'start' : 'end'}
          dominantBaseline="middle"
          fontSize={10}
          fill={payload.prev == null ? 'var(--text-muted)' : deltaColor(value, payload.prev, payload.type)}
        >
          {payload.prev == null ? 'new' : formatDelta(value, payload.prev, formatMoney)}
        </text>
      )}
    </g>
  )
}

interface TooltipData {
  name?: string
  value?: number
  type?: string
  id?: string
  prev?: number | null
}

function SankeyTooltip({
  active,
  payload,
  groupCategories,
  categoryPayees,
  isDrilled,
}: {
  active?: boolean
  payload?: Array<{ payload: TooltipData }>
  groupCategories: Record<string, CategoryPayee[]>
  categoryPayees: Record<string, CategoryPayee[]>
  isDrilled: boolean
}) {
  const { formatMoney } = useFormatters()
  if (!active || !payload?.length) return null
  const p = payload[0]?.payload
  const name = p?.name ?? ''
  const value = p?.value ?? 0
  const nodeId = p?.id
  const nodeType = p?.type

  let items: CategoryPayee[] = []
  let itemsLabel = ''

  if (nodeType === 'category_group' && !isDrilled && nodeId) {
    items = groupCategories[nodeId] ?? []
    itemsLabel = 'Top categories'
  } else if (nodeType === 'category' && nodeId) {
    items = categoryPayees[nodeId] ?? []
    itemsLabel = 'Top payees'
  }

  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip__label">{name}</div>
      <div className="chart-tooltip__row">
        <span className="chart-tooltip__name">Amount</span>
        <span className="chart-tooltip__value">{formatMoney(value)}</span>
      </div>
      {p?.prev !== undefined && (
        <>
          <div className="chart-tooltip__row">
            <span className="chart-tooltip__name">Previous</span>
            <span className="chart-tooltip__value">
              {p.prev == null ? '—' : formatMoney(p.prev)}
            </span>
          </div>
          {p.prev != null && (
            <div className="chart-tooltip__row">
              <span className="chart-tooltip__name">Change</span>
              <span
                className="chart-tooltip__value"
                style={{ color: deltaColor(value, p.prev, nodeType ?? '') }}
              >
                {formatDelta(value, p.prev, formatMoney)}
              </span>
            </div>
          )}
        </>
      )}
      {items.length > 0 && (
        <>
          <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-muted)' }}>{itemsLabel}</div>
          {items.slice(0, 8).map((item) => (
            <div key={item.name} className="chart-tooltip__row">
              <span className="chart-tooltip__name">{item.name}</span>
              <span className="chart-tooltip__value">{formatMoney(Number(item.total))}</span>
            </div>
          ))}
        </>
      )}
    </div>
  )
}

export function CashFlowSankeyReport({ budgetId }: Props) {
  const chartHeight = useChartHeight(500)
  const { formatMoney } = useFormatters()
  const { filters, setDrillDown } = useReportStore()
  const [viewMode, setViewMode] = useState<'spent' | 'budgeted'>('spent')
  const [compare, setCompare] = useState(false)
  const acctIds = filters.accountIds.length > 0 ? filters.accountIds : undefined
  const { data, isLoading, isError, error, refetch } = useCashFlowReport(budgetId, filters.startDate, filters.endDate, viewMode, acctIds)
  const prevWindow = previousWindow(filters.startDate, filters.endDate)
  const { data: prevData } = useCashFlowReport(
    budgetId, prevWindow.start, prevWindow.end, viewMode, acctIds, { enabled: compare },
  )
  const { data: allPayees } = usePayees(budgetId)
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null)
  const [selectedCategoryId, setSelectedCategoryId] = useState<string | null>(null)
  const captureRef = useRef<HTMLDivElement>(null)

  // Reset drill-down and comparison when switching modes
  const handleModeChange = (mode: 'spent' | 'budgeted') => {
    setViewMode(mode)
    setSelectedGroupId(null)
    setSelectedCategoryId(null)
    setCompare(false)
  }

  // Previous-window totals keyed by the backend's stable node ids (g_/c_...),
  // so deltas survive drilling. Payees have no ids at level 3 — match by name.
  const prevTotals = useMemo(
    () => (compare && prevData ? extractPrevTotals(prevData) : null),
    [compare, prevData],
  )

  // Build simplified sankey: Income → Groups → Categories → Payees (each level on drill)
  const { sankeyData, groupCategories, categoryPayees } = useMemo(
    () => buildSankeyView(data, selectedGroupId, selectedCategoryId, prevTotals, prevData),
    [data, selectedGroupId, selectedCategoryId, prevTotals, prevData],
  )

  const selectedGroupName = selectedGroupId
    ? data?.nodes.find((n) => n.id === selectedGroupId)?.name ?? null
    : null
  const selectedCategoryName = selectedCategoryId
    ? data?.nodes.find((n) => n.id === selectedCategoryId)?.name ?? null
    : null

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  if (!sankeyData.nodes.length) {
    return (
      <div className="report-section">
        <h2 className="report-section__title">Cash Flow</h2>
        <div className="reports-empty">No transaction data for this period.</div>
      </div>
    )
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleClick = (item: any, type: string) => {
    if (type !== 'node') return
    const nodeData = item?.payload as NodeData | undefined
    if (!nodeData) return

    const window = { startDate: filters.startDate, endDate: filters.endDate }

    if (nodeData.type === 'income') {
      if (selectedGroupId || selectedCategoryId) {
        // Clicking income while drilled resets to all groups
        setSelectedGroupId(null)
        setSelectedCategoryId(null)
      } else if (viewMode === 'spent') {
        // At the top level it opens the income transactions instead
        setDrillDown({
          kind: 'month', label: 'Income', scope: 'parent', direction: 'inflow', ...window,
        })
      }
    } else if (nodeData.type === 'category_group') {
      if (selectedCategoryId) {
        // Go back to group level
        setSelectedCategoryId(null)
      } else if (!selectedGroupId) {
        // Drill into group
        setSelectedGroupId(nodeData.id)
      }
    } else if (nodeData.type === 'category' && selectedGroupId && viewMode === 'spent') {
      if (!selectedCategoryId) {
        // Drill into category to show payees (only in spent mode)
        setSelectedCategoryId(nodeData.id)
      } else {
        // Already at payee level — the category node opens its transactions
        setDrillDown({
          kind: 'category', label: nodeData.name, scope: 'leaf', direction: 'outflow',
          // entity_id, not the node id: the id is a (group, category)
          // composite so one category can appear under both its own group and
          // the savings trunk, and stripping the prefix yielded a non-UUID.
          categoryIds: [nodeData.entity_id ?? nodeData.id.replace(/^c_/, '')], ...window,
        })
      }
    } else if (nodeData.type === 'payee') {
      // Level-3 payee nodes carry names only — resolve back to an id
      const payeeId = (allPayees ?? []).find((p) => p.name === nodeData.name)?.id
      if (payeeId) {
        setDrillDown({
          kind: 'payee', label: nodeData.name, scope: 'parent', direction: 'outflow',
          payeeIds: [payeeId], ...window,
        })
      }
    }
  }

  const resetToGroups = () => {
    setSelectedGroupId(null)
    setSelectedCategoryId(null)
  }

  const resetToCategories = () => {
    setSelectedCategoryId(null)
  }

  return (
    <div className="report-section">
      <div className="report-section__header">
        <h2 className="report-section__title">Cash Flow</h2>
        <ReportInfoButton title="Cash Flow Sankey">
          <p>Shows how <strong>income flows into category groups</strong>. Band width = dollar amount.</p>
          <p><strong>Spent</strong>: actual transactions — drill down to payees. <strong>Budgeted</strong>: budget assignments — drill down to categories only. Assignments aren't tied to accounts, so in Budgeted mode the account filter applies to the income total only.</p>
          <p><strong>Compare</strong> overlays the change versus the preceding period of equal length on every node. In Spent mode, clicking a payee node (or a category node at the payee level) lists the transactions behind it below the chart.</p>
          <ReportScopeNote scope="on-budget-filterable" />
        </ReportInfoButton>
        <div className="report-toggle-group">
          <button
            className={`report-toggle-btn${viewMode === 'spent' ? ' report-toggle-btn--active' : ''}`}
            onClick={() => handleModeChange('spent')}
          >
            Spent
          </button>
          <button
            className={`report-toggle-btn${viewMode === 'budgeted' ? ' report-toggle-btn--active' : ''}`}
            onClick={() => handleModeChange('budgeted')}
          >
            Budgeted
          </button>
        </div>
        <button
          className={`report-btn${compare ? ' report-btn--active' : ''}`}
          onClick={() => setCompare((c) => !c)}
          title={`Compare with ${prevWindow.start} – ${prevWindow.end}`}
          type="button"
        >
          Compare
        </button>
        <ReportExportButton
          reportId="cash-flow"
          getRows={() => {
            if (!data) return []
            const nodeName = new Map(data.nodes.map((n) => [n.id, n.name]))
            const rows: Record<string, unknown>[] = data.links.map((l) => ({
              source: nodeName.get(l.source) ?? l.source,
              target: nodeName.get(l.target) ?? l.target,
              value: Number(l.value),
            }))
            rows.push({ source: 'TOTAL', target: 'income', value: Number(data.total_income) })
            rows.push({ source: 'TOTAL', target: 'expenses', value: Number(data.total_expense) })
            return rows
          }}
          captureRef={captureRef}
          window={{ start: filters.startDate, end: filters.endDate }}
        />
        <div className="sankey-breadcrumb">
          <button className="sankey-crumb" onClick={resetToGroups}>
            All Groups
          </button>
          {selectedGroupName && (
            <>
              <ChevronRight size={14} className="sankey-crumb-sep" />
              <button className="sankey-crumb" onClick={resetToCategories}>
                {selectedGroupName}
              </button>
            </>
          )}
          {selectedCategoryName && (
            <>
              <ChevronRight size={14} className="sankey-crumb-sep" />
              <span className="sankey-crumb sankey-crumb--active">{selectedCategoryName}</span>
            </>
          )}
        </div>
      </div>
      <p className="report-section__subtitle">
        {selectedCategoryName
          ? `Showing payees for ${selectedCategoryName}.`
          : selectedGroupName
            ? `Showing categories in ${selectedGroupName}.${viewMode === 'spent' ? ' Click a category to see payees.' : ''}`
            : 'Click a category group to drill down.'}
      </p>

      <div ref={captureRef} className="report-capture">
      {data && (
        <div className="report-metrics">
          <MetricCard
            label="Total Income"
            value={formatMoney(Number(data.total_income))}
            sub={compare && prevData ? formatDelta(Number(data.total_income), Number(prevData.total_income), formatMoney) : undefined}
          />
          {/* total_expense is ALL outflow, including the savings and debt
              trunks now drawn as their own branches — labelling it "Expenses"
              put $5,000 above a diagram showing $3,000 into expense groups,
              and disagreed with Income vs Expenses for the same window. */}
          <MetricCard
            label="Spent"
            value={formatMoney(Number(data.total_spending))}
            sub={compare && prevData ? formatDelta(Number(data.total_spending), Number(prevData.total_spending), formatMoney) : undefined}
          />
          {Number(data.total_savings) > 0 && (
            <MetricCard label="Saved" value={formatMoney(Number(data.total_savings))} />
          )}
          {Number(data.total_debt_principal) > 0 && (
            <MetricCard
              label="Debt Paid"
              value={formatMoney(Number(data.total_debt_principal))}
            />
          )}
          {/* Net still uses the whole outflow: everything that left the
              budget did leave, however it is branched. */}
          <MetricCard
            label="Net"
            value={formatMoney(Number(data.total_income) - Number(data.total_expense))}
            sub={
              compare && prevData
                ? formatDelta(
                    Number(data.total_income) - Number(data.total_expense),
                    Number(prevData.total_income) - Number(prevData.total_expense),
                    formatMoney,
                  )
                : undefined
            }
          />
        </div>
      )}

      {compare && prevData && (
        <p className="report-section__subtitle">
          Compared with {prevWindow.start} – {prevWindow.end} (previous period of equal length).
          Groups or payees with no spending this period are not shown.
        </p>
      )}

      <ResponsiveContainer width="100%" height={chartHeight}>
        <Sankey
          data={sankeyData}
          nodePadding={14}
          margin={{ top: 10, right: 200, bottom: 10, left: 100 }}
          node={<SankeyNodeRect />}
          link={{ stroke: 'var(--border-color)', strokeOpacity: 0.5 }}
          onClick={handleClick}
        >
          <Tooltip
            offset={16}
            isAnimationActive={false}
            content={(props) => (
              <SankeyTooltip
                active={props.active}
                payload={props.payload as unknown as Array<{ payload: TooltipData }>}
                groupCategories={groupCategories}
                categoryPayees={categoryPayees}
                isDrilled={!!selectedGroupId}
              />
            )}
          />
        </Sankey>
      </ResponsiveContainer>

      <div className="sankey-legend">
        <div className="sankey-legend__item">
          <span className="sankey-legend__dot" style={{ background: NODE_COLORS.income }} />
          <span>income</span>
        </div>
        <div className="sankey-legend__item">
          <span className="sankey-legend__dot" style={{ background: NODE_COLORS.category_group }} />
          <span>category group</span>
        </div>
        {selectedGroupId && (
          <div className="sankey-legend__item">
            <span className="sankey-legend__dot" style={{ background: NODE_COLORS.category }} />
            <span>category</span>
          </div>
        )}
        {selectedCategoryId && (
          <div className="sankey-legend__item">
            <span className="sankey-legend__dot" style={{ background: NODE_COLORS.payee }} />
            <span>payee</span>
          </div>
        )}
      </div>
      </div>
    </div>
  )
}
