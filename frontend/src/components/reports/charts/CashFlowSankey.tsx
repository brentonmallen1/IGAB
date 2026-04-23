import { useState, useMemo } from 'react'
import { ChevronRight } from 'lucide-react'
import { useReportStore } from '../../../stores/reportStore'
import { useCashFlowReport } from '../../../api/reports'
import { formatMoney } from '../../../utils/money'
import { MetricCard } from '../MetricCard'
import { Sankey, Tooltip, ResponsiveContainer } from 'recharts'
import { ReportInfoButton } from '../ReportInfoButton'
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
}

function SankeyNodeRect(props: {
  x?: number; y?: number; width?: number; height?: number
  payload?: NodeData
}) {
  const { x = 0, y = 0, width = 0, height = 0, payload } = props
  if (!payload) return null
  const isLeft = payload.type === 'income'
  const color = NODE_COLORS[payload.type] ?? '#999'
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} fill={color} />
      <text
        x={isLeft ? x + width + 6 : x - 6}
        y={y + height / 2}
        textAnchor={isLeft ? 'start' : 'end'}
        dominantBaseline="middle"
        fontSize={12}
        fill={color}
        fontWeight={500}
      >
        {payload.name.length > 24 ? payload.name.slice(0, 22) + '…' : payload.name}
      </text>
    </g>
  )
}

interface TooltipData {
  name?: string
  value?: number
  type?: string
  id?: string
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
  const { filters } = useReportStore()
  const [viewMode, setViewMode] = useState<'spent' | 'budgeted'>('spent')
  const acctIds = filters.accountIds.length > 0 ? filters.accountIds : undefined
  const { data, isLoading } = useCashFlowReport(budgetId, filters.startDate, filters.endDate, viewMode, acctIds)
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null)
  const [selectedCategoryId, setSelectedCategoryId] = useState<string | null>(null)

  // Reset drill-down when switching modes
  const handleModeChange = (mode: 'spent' | 'budgeted') => {
    setViewMode(mode)
    setSelectedGroupId(null)
    setSelectedCategoryId(null)
  }

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

    return {
      sankeyData: { nodes, links: links.filter((l) => l.value > 0) },
      groupCategories: data.group_categories ?? {},
      categoryPayees: data.category_payees ?? {},
    }
  }, [data, selectedGroupId, selectedCategoryId])

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

    if (nodeData.type === 'income') {
      // Clicking income resets to all groups
      setSelectedGroupId(null)
      setSelectedCategoryId(null)
    } else if (nodeData.type === 'category_group') {
      if (selectedCategoryId) {
        // Go back to group level
        setSelectedCategoryId(null)
      } else if (!selectedGroupId) {
        // Drill into group
        setSelectedGroupId(nodeData.id)
      }
    } else if (nodeData.type === 'category' && selectedGroupId && !selectedCategoryId && viewMode === 'spent') {
      // Drill into category to show payees (only in spent mode)
      setSelectedCategoryId(nodeData.id)
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

      {data && (
        <div className="report-metrics">
          <MetricCard label="Total Income" value={formatMoney(Number(data.total_income))} />
          <MetricCard label="Total Expenses" value={formatMoney(Number(data.total_expense))} />
          <MetricCard label="Net" value={formatMoney(Number(data.total_income) - Number(data.total_expense))} />
        </div>
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
  )
}
