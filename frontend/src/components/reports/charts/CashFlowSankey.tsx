import { useState, useMemo, useRef } from 'react'
import { ChevronRight } from 'lucide-react'
import { incomeDrill, useReportStore } from '../../../stores/reportStore'
import { useCashFlowReport } from '../../../api/reports'
import { usePayees } from '../../../api/payees'
import { useChartHeight } from '../../../hooks/useChartHeight'
import { useFormatters } from '../../../hooks/useFormatters'
import { ReportErrorState } from '../ReportErrorState'
import { previousWindow } from '../../../utils/dateWindow'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { CHART_COLORS, COLOR_NEGATIVE, COLOR_POSITIVE } from './chartColors'
import { Sankey, Tooltip, ResponsiveContainer } from 'recharts'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import type { CashFlowReport, CategoryPayee } from '../../../types'
import {
  buildSankeyView,
  categoryNodeDrill,
  deltaColor,
  extractPrevTotals,
  formatDelta,
  sankeyExportRows,
  sankeyGeometry,
  sankeyHeight,
  sankeyNodePadding,
  type SankeyViewNode,
} from './sankeyView'
import './CashFlowSankey.css'
import { truncateLabel } from '../../../utils/truncateLabel'

interface Props {
  budgetId: string
}

/** Colour by what a node is, not by where it sits: money in, the hub, where
 *  it went, and the two balancing nodes by their meaning. */
const NODE_COLORS: Record<string, string> = {
  income_payee: COLOR_POSITIVE,
  inflow: CHART_COLORS[4],
  shortfall: COLOR_NEGATIVE,
  budget: 'var(--text-muted)',
  category_group: CHART_COLORS[1],
  category: CHART_COLORS[3],
  payee: CHART_COLORS[2],
  left_over: COLOR_POSITIVE,
}

type NodeData = SankeyViewNode

function SankeyNodeRect(props: {
  x?: number
  y?: number
  width?: number
  height?: number
  labelChars?: number
  payload?: NodeData & { value?: number; depth?: number }
}) {
  const { formatMoney, privacyMode } = useFormatters()
  const { x = 0, y = 0, width = 0, height = 0, payload, labelChars = 24 } = props
  if (!payload) return null
  // The first column labels to its left, into the left margin; every other
  // column to its right — the last into the right margin.
  const isLeft = (payload.depth ?? 0) === 0
  const color = NODE_COLORS[payload.type] ?? 'var(--text-muted)'
  const value = payload.value ?? 0
  const hasDelta = payload.prev !== undefined
  const tx = isLeft ? x - 6 : x + width + 6
  const anchor = isLeft ? 'end' : 'start'
  const mid = y + height / 2
  const top = mid - (hasDelta ? 12 : 6)
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} fill={color} />
      <text
        x={tx}
        y={top}
        textAnchor={anchor}
        dominantBaseline="middle"
        fontSize={12}
        fill="var(--text-primary)"
        fontWeight={500}
      >
        {truncateLabel(payload.name, labelChars)}
      </text>
      <text
        x={tx}
        y={top + 13}
        textAnchor={anchor}
        dominantBaseline="middle"
        fontSize={11}
        fill="var(--text-secondary)"
        className="tabular"
      >
        {formatMoney(value)}
      </text>
      {hasDelta && (
        <text
          x={tx}
          y={top + 26}
          textAnchor={anchor}
          dominantBaseline="middle"
          fontSize={10}
          fill={
            payload.prev == null
              ? 'var(--text-muted)'
              : deltaColor(value, payload.prev, payload.type)
          }
        >
          {payload.prev == null
            ? 'new'
            : formatDelta(value, payload.prev, formatMoney, privacyMode)}
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
  const { formatMoney, formatMoneyOrDash, privacyMode } = useFormatters()
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
            <span className="chart-tooltip__value">{formatMoneyOrDash(p.prev)}</span>
          </div>
          {p.prev != null && (
            <div className="chart-tooltip__row">
              <span className="chart-tooltip__name">Change</span>
              <span
                className="chart-tooltip__value"
                style={{ color: deltaColor(value, p.prev, nodeType ?? '') }}
              >
                {formatDelta(value, p.prev, formatMoney, privacyMode)}
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
              <span className="chart-tooltip__value">{formatMoney(item.total)}</span>
            </div>
          ))}
        </>
      )}
    </div>
  )
}

/** The class cards: net figures, named by which way they went — a month that
 *  drew more out of savings than it put in did not "move to savings". */
function ClassCards({
  data,
  prevData,
  compare,
}: {
  data: CashFlowReport
  prevData: CashFlowReport | undefined
  compare: boolean
}) {
  const { formatMoney, privacyMode } = useFormatters()
  if (data.total_spending === null) return null
  const savings = Number(data.total_savings)
  const debt = Number(data.total_debt_principal)
  return (
    <>
      <MetricCard
        label="Spent"
        value={formatMoney(Number(data.total_spending))}
        sub={
          compare && prevData && prevData.total_spending !== null
            ? formatDelta(
                Number(data.total_spending),
                Number(prevData.total_spending),
                formatMoney,
                privacyMode
              )
            : 'net of refunds'
        }
      />
      {/* Money moved — the "To savings accounts" trunk. Not "Saved": that
          figure (Savings Rate) adds what kept-here envelopes hold, which
          never left the budget and is not on this diagram. */}
      {savings !== 0 && (
        <MetricCard
          label={savings > 0 ? 'Moved to savings' : 'Drawn from savings'}
          value={formatMoney(Math.abs(savings))}
        />
      )}
      {debt !== 0 && (
        <MetricCard
          label={debt > 0 ? 'Debt paid' : 'Borrowed'}
          value={formatMoney(Math.abs(debt))}
        />
      )}
    </>
  )
}

export function CashFlowSankeyReport({ budgetId }: Props) {
  const chartHeight = useChartHeight(500)
  const { formatMoney, privacyMode } = useFormatters()
  const { filters, setDrillDown } = useReportStore()
  const [viewMode, setViewMode] = useState<'spent' | 'budgeted'>('spent')
  const [compare, setCompare] = useState(false)
  // The width the chart is drawn at, for margins in proportion to it.
  const [chartWidth, setChartWidth] = useState(800)
  const acctIds = filters.accountIds.length > 0 ? filters.accountIds : undefined
  const { data, isLoading, isError, error, refetch } = useCashFlowReport(
    budgetId,
    filters.startDate,
    filters.endDate,
    viewMode,
    acctIds
  )
  const prevWindow = previousWindow(filters.startDate, filters.endDate)
  const { data: prevData } = useCashFlowReport(
    budgetId,
    prevWindow.start,
    prevWindow.end,
    viewMode,
    acctIds,
    { enabled: compare }
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

  // Previous-window totals keyed by the backend's stable node ids, so deltas
  // survive drilling. Payees have no ids at level 3 — match by name.
  const prevTotals = useMemo(
    () => (compare && prevData ? extractPrevTotals(prevData) : null),
    [compare, prevData]
  )

  const { sankeyData, groupCategories, categoryPayees } = useMemo(
    () => buildSankeyView(data, selectedGroupId, selectedCategoryId, prevTotals, prevData),
    [data, selectedGroupId, selectedCategoryId, prevTotals, prevData]
  )
  const geometry = sankeyGeometry(chartWidth)

  const selectedGroupName = selectedGroupId
    ? (data?.nodes.find((n) => n.id === selectedGroupId)?.name ?? null)
    : null
  const selectedCategoryName = selectedCategoryId
    ? (data?.nodes.find((n) => n.id === selectedCategoryId)?.name ?? null)
    : null

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  if (!sankeyData.nodes.length) {
    return (
      <div className="report-section surface">
        <h2 className="report-section__title">Where the money went</h2>
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
    const category = selectedCategoryId
      ? data?.nodes.find((n) => n.id === selectedCategoryId)
      : null

    if (nodeData.type === 'budget') {
      // The hub steps back out to every group.
      setSelectedGroupId(null)
      setSelectedCategoryId(null)
    } else if (nodeData.type === 'income_payee' && viewMode === 'spent') {
      setDrillDown(incomeDrill('Income', window))
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
        // Already at payee level — the category node opens its transactions.
        // entity_id, never the node id: the id is a (group, category)
        // composite, and stripping its prefix posted a non-UUID.
        setDrillDown(categoryNodeDrill(nodeData, window))
      }
    } else if (nodeData.type === 'payee') {
      // Level-3 payee nodes carry names only — resolve back to an id. The
      // payee's band is its net inside this category, so the list is too:
      // both directions, this category's rows, the classes it counted.
      const payeeId = (allPayees ?? []).find((p) => p.name === nodeData.name)?.id
      if (payeeId) {
        setDrillDown({
          kind: 'payee',
          label: nodeData.name,
          scope: 'leaf',
          payeeIds: [payeeId],
          categoryIds: category?.entity_id ? [category.entity_id] : undefined,
          activityClasses: category?.activity_classes ?? undefined,
          ...window,
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

  const net = data?.net === null || data?.net === undefined ? null : Number(data.net)
  const prevNet =
    prevData?.net === null || prevData?.net === undefined ? null : Number(prevData.net)
  const assigned =
    data?.total_assigned === null || data?.total_assigned === undefined
      ? null
      : Number(data.total_assigned)

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Where the money went</h2>
        <ReportInfoButton title="Cash Flow — where the money went">
          <p>
            What came in on the left, where it went on the right. Band width is the amount, and
            every node says it.
          </p>
          <p>
            <strong>Spent</strong> is net, as Income vs Expenses counts it: a refund comes off its
            category, money drawn back out of savings comes off what was moved there, and new
            borrowing comes off what was repaid. What nets the other way is drawn on the left —
            Refunds, From savings, Borrowed. <strong>Left over</strong> is what came in and did not
            go out; a <strong>Shortfall</strong> is what went out beyond what came in. Either one is
            the Net card, the same figure Income vs Expenses gives this window.
          </p>
          <p>
            <strong>Budgeted</strong> draws the money assigned instead, netted per category: money
            moved out of one category into another is drawn once, with what the first gave up as a
            source of its own. Assignments aren&apos;t tied to accounts, so the account filter
            applies to the income figure only.
          </p>
          <p>
            Click a group to see its categories, and a category (in Spent) to see its payees.{' '}
            <strong>Compare</strong> shows the change against the preceding period of equal length
            on every node.
          </p>
          <ReportScopeNote report="cash-flow" />
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
          getRows={() => (data ? sankeyExportRows(data) : [])}
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
          <MetricRow>
            <MetricCard
              label="Income"
              value={formatMoney(data.total_income)}
              sub={
                compare && prevData
                  ? formatDelta(data.total_income, prevData.total_income, formatMoney, privacyMode)
                  : undefined
              }
            />
            <ClassCards data={data} prevData={prevData} compare={compare} />
            {net !== null && (
              <MetricCard
                label="Net"
                value={formatMoney(net)}
                sub={
                  compare && prevNet !== null
                    ? formatDelta(net, prevNet, formatMoney, privacyMode)
                    : net >= 0
                      ? 'left over'
                      : 'shortfall'
                }
              />
            )}
            {/* Budgeted mode: what was assigned, and how it stands against
              income. Not "Net" — income less assigned is not the growth of
              anything, and the name put it beside spent mode's Net. */}
            {assigned !== null && (
              <>
                <MetricCard
                  label="Assigned"
                  value={formatMoney(assigned)}
                  sub="net of re-planning"
                />
                <MetricCard
                  label="Income less assigned"
                  value={formatMoney(data.total_income - assigned)}
                />
              </>
            )}
          </MetricRow>
        )}

        {compare && prevData && (
          <p className="report-section__subtitle">
            Compared with {prevWindow.start} – {prevWindow.end} (previous period of equal length).
            Groups or payees with no spending this period are not shown.
          </p>
        )}

        <ResponsiveContainer
          width="100%"
          height={sankeyHeight(sankeyData, chartHeight, compare)}
          onResize={(w) => setChartWidth(Math.round(w))}
        >
          <Sankey
            data={sankeyData}
            nodePadding={sankeyNodePadding(compare)}
            // The served order: income, then what came back, then the balancing
            // node; groups by size, then Left over. Sorting by size mixed them.
            sort={false}
            margin={{ top: 12, right: geometry.right, bottom: 12, left: geometry.left }}
            node={<SankeyNodeRect labelChars={geometry.labelChars} />}
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
          {(
            [
              ['income_payee', 'money in'],
              ['inflow', 'other money in'],
              ['category_group', 'where it went'],
              ['left_over', 'left over'],
              ['shortfall', 'shortfall'],
            ] as const
          )
            .filter(([type]) => sankeyData.nodes.some((n) => n.type === type))
            .map(([type, label]) => (
              <div key={type} className="sankey-legend__item">
                <span className="sankey-legend__dot" style={{ background: NODE_COLORS[type] }} />
                <span>{label}</span>
              </div>
            ))}
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
