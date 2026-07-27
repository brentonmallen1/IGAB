import { useState, useMemo, useRef } from 'react'
import { ChevronRight } from 'lucide-react'
import { useReportStore } from '../../../stores/reportStore'
import { useCashFlowReport } from '../../../api/reports'
import { usePayees } from '../../../api/payees'
import { useFormatters } from '../../../hooks/useFormatters'
import { previousWindow } from '../../../utils/dateWindow'
import { MetricCard } from '../MetricCard'
import { Sankey, Tooltip, ResponsiveContainer } from 'recharts'
import { ReportInfoButton } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import type { CategoryPayee } from '../../../types'
import './CashFlowSankey.css'

interface Props { budgetId: string }

const NODE_COLORS: Record<string, string> = {
  income: '#59a14f',
  category_group: '#f28e2b',
  category: '#edc948',
  payee: '#e15759',
}

interface NodeData {
  name: string
  type: string
  id: string
  /** Previous-window value when compare is on; null = node is new this window */
  prev?: number | null
}

/** Signed delta as "+$123 (+12%)"; pct omitted when prev is 0. */
function formatDelta(current: number, prev: number, formatMoney: (n: number) => string): string {
  const delta = current - prev
  const sign = delta >= 0 ? '+' : '−'
  const amount = `${sign}${formatMoney(Math.abs(delta))}`
  if (prev === 0) return amount
  return `${amount} (${sign}${Math.abs((delta / prev) * 100).toFixed(0)}%)`
}

/** For income more is good; for expense-side nodes more is bad. */
function deltaColor(current: number, prev: number, type: string): string {
  const increased = current >= prev
  const good = type === 'income' ? increased : !increased
  return good ? 'var(--color-positive)' : 'var(--color-negative)'
}

function SankeyNodeRect(props: {
  x?: number; y?: number; width?: number; height?: number
  payload?: NodeData & { value?: number }
}) {
  const { formatMoney } = useFormatters()
  const { x = 0, y = 0, width = 0, height = 0, payload } = props
  if (!payload) return null
  const isLeft = payload.type === 'income'
  const color = NODE_COLORS[payload.type] ?? '#999'
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
        fill={color}
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
  const { formatMoney } = useFormatters()
  const { filters, setDrillDown } = useReportStore()
  const [viewMode, setViewMode] = useState<'spent' | 'budgeted'>('spent')
  const [compare, setCompare] = useState(false)
  const acctIds = filters.accountIds.length > 0 ? filters.accountIds : undefined
  const { data, isLoading } = useCashFlowReport(budgetId, filters.startDate, filters.endDate, viewMode, acctIds)
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
  const prevTotals = useMemo(() => {
    if (!compare || !prevData) return null
    const groups = new Map<string, number>()
    const cats = new Map<string, number>()
    const nodeType = new Map(prevData.nodes.map((n) => [n.id, n.type]))
    for (const link of prevData.links) {
      if (link.source === '__budget__') {
        groups.set(link.target, Number(link.value))
      } else if (nodeType.get(link.source) === 'category_group') {
        cats.set(link.target, Number(link.value))
      }
    }
    return { groups, cats }
  }, [compare, prevData])

  // Build simplified sankey: Income → Groups → Categories → Payees (each level on drill)
  const { sankeyData, groupCategories, categoryPayees } = useMemo(() => {
    if (!data || data.nodes.length === 0) {
      return {
        sankeyData: { nodes: [], links: [] },
        groupCategories: {} as Record<string, CategoryPayee[]>,
        categoryPayees: {} as Record<string, CategoryPayee[]>,
      }
    }

    const groups = data.nodes.filter((n) => n.type === 'category_group')
    const categories = data.nodes.filter((n) => n.type === 'category')

    // Calculate total per group from budget→group links
    const groupTotals = new Map<string, number>()
    for (const link of data.links) {
      if (link.source === '__budget__') {
        groupTotals.set(link.target, Number(link.value))
      }
    }

    // Calculate total per category
    const catTotals = new Map<string, number>()
    for (const link of data.links) {
      const sourceNode = data.nodes.find((n) => n.id === link.source)
      if (sourceNode?.type === 'category_group') {
        catTotals.set(link.target, Number(link.value))
      }
    }

    const nodes: NodeData[] = []
    const links: { source: number; target: number; value: number }[] = []

    // Single income node always first
    nodes.push({ id: '__income__', name: 'Income', type: 'income' })

    if (selectedCategoryId && selectedGroupId) {
      // Level 3: Income → Group → Category → Payees
      const group = groups.find((g) => g.id === selectedGroupId)
      const category = categories.find((c) => c.id === selectedCategoryId)
      const payees = data.category_payees[selectedCategoryId] ?? []

      if (group && category) {
        nodes.push({ id: group.id, name: group.name, type: 'category_group' })
        nodes.push({ id: category.id, name: category.name, type: 'category' })
        links.push({ source: 0, target: 1, value: groupTotals.get(group.id) ?? 0 })
        links.push({ source: 1, target: 2, value: catTotals.get(category.id) ?? 0 })

        payees.forEach((payee, i) => {
          nodes.push({ id: `payee_${i}`, name: payee.name, type: 'payee' })
          links.push({ source: 2, target: 3 + i, value: Number(payee.total) })
        })
      }
    } else if (selectedGroupId) {
      // Level 2: Income → Group → Categories
      const group = groups.find((g) => g.id === selectedGroupId)
      if (group) {
        nodes.push({ id: group.id, name: group.name, type: 'category_group' })
        links.push({ source: 0, target: 1, value: groupTotals.get(group.id) ?? 0 })

        const groupCats = categories.filter((c) =>
          data.links.some((l) => l.source === group.id && l.target === c.id)
        )
        groupCats.forEach((cat, i) => {
          nodes.push({ id: cat.id, name: cat.name, type: 'category' })
          links.push({ source: 1, target: 2 + i, value: catTotals.get(cat.id) ?? 0 })
        })
      }
    } else {
      // Level 1: Income → Groups
      groups.forEach((group, i) => {
        nodes.push({ id: group.id, name: group.name, type: 'category_group' })
        links.push({ source: 0, target: 1 + i, value: groupTotals.get(group.id) ?? 0 })
      })
    }

    // Attach previous-window values for the compare overlay. null = new node.
    if (prevTotals) {
      const prevPayees = selectedCategoryId
        ? new Map(
            (prevData?.category_payees[selectedCategoryId] ?? []).map((p) => [p.name, Number(p.total)]),
          )
        : null
      // The synthetic Income node's value is the sum of visible outflows, not
      // income — its delta lives on the metric cards instead
      for (const node of nodes) {
        if (node.type === 'category_group') node.prev = prevTotals.groups.get(node.id) ?? null
        else if (node.type === 'category') node.prev = prevTotals.cats.get(node.id) ?? null
        else if (node.type === 'payee') node.prev = prevPayees?.get(node.name) ?? null
      }
    }

    return {
      sankeyData: { nodes, links: links.filter((l) => l.value > 0) },
      groupCategories: data.group_categories ?? {},
      categoryPayees: data.category_payees ?? {},
    }
  }, [data, selectedGroupId, selectedCategoryId, prevTotals, prevData])

  const selectedGroupName = selectedGroupId
    ? data?.nodes.find((n) => n.id === selectedGroupId)?.name ?? null
    : null
  const selectedCategoryName = selectedCategoryId
    ? data?.nodes.find((n) => n.id === selectedCategoryId)?.name ?? null
    : null

  if (isLoading) return <div className="report-loading">Loading…</div>

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
          categoryIds: [nodeData.id.replace(/^c_/, '')], ...window,
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
      <div className="report-section__controls">
        <h2 className="report-section__title">Cash Flow</h2>
        <ReportInfoButton title="Cash Flow Sankey">
          <p>Shows how <strong>income flows into category groups</strong>. Band width = dollar amount.</p>
          <p><strong>Spent</strong>: actual transactions — drill down to payees. <strong>Budgeted</strong>: budget assignments — drill down to categories only.</p>
          <p><strong>Compare</strong> overlays the change versus the preceding period of equal length on every node. In Spent mode, clicking a payee node (or a category node at the payee level) lists the transactions behind it below the chart.</p>
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
          <MetricCard
            label="Total Expenses"
            value={formatMoney(Number(data.total_expense))}
            sub={compare && prevData ? formatDelta(Number(data.total_expense), Number(prevData.total_expense), formatMoney) : undefined}
          />
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

      <ResponsiveContainer width="100%" height={500}>
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
