import { useState, useMemo, useRef } from 'react'
import { Treemap, ResponsiveContainer, Tooltip } from 'recharts'
import { ChevronRight } from 'lucide-react'
import { useReportStore } from '../../../stores/reportStore'
import { useSpendingGroupedReport } from '../../../api/reports'
import { useChartHeight } from '../../../hooks/useChartHeight'
import { useFormatters } from '../../../hooks/useFormatters'
import { ReportErrorState } from '../ReportErrorState'
import { chartColor } from './chartColors'
import { ReportInfoButton } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import './SpendingTreemap.css'

interface Props { budgetId: string }

interface TreeNode {
  name: string
  id: string
  parent_id: string | null
  parent_name: string | null
  size: number
  pct: number
  fill?: string
  // Recharts' Treemap data points must satisfy TreemapDataType's index signature.
  [key: string]: unknown
}

export function SpendingTreemapReport({ budgetId }: Props) {
  const chartHeight = useChartHeight(440)
  const { formatMoney } = useFormatters()
  const { filters, setDrillDown } = useReportStore()
  const groupBy = filters.groupBy
  const catIds = filters.categoryIds.length > 0 ? filters.categoryIds : undefined
  const acctIds = filters.accountIds.length > 0 ? filters.accountIds : undefined
  const [hideSavings, setHideSavings] = useState(false)
  const { data, isLoading, isError, refetch } = useSpendingGroupedReport(budgetId, filters.startDate, filters.endDate, catIds, acctIds, hideSavings)
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null)
  const captureRef = useRef<HTMLDivElement>(null)

  // Reset the drill when the group-by mode changes (state adjusted during
  // render instead of in an effect, per react-hooks/set-state-in-effect)
  const [prevGroupBy, setPrevGroupBy] = useState(groupBy)
  if (prevGroupBy !== groupBy) {
    setPrevGroupBy(groupBy)
    setSelectedGroup(null)
  }

  const items = useMemo(() => data?.groups ?? [], [data])
  const grandTotal = Number(data?.total ?? 0)

  const groups = useMemo(() => {
    const map = new Map<string, { name: string; total: number; colorIdx: number; children: TreeNode[] }>()
    let colorIdx = 0
    for (const item of items) {
      const gid = item.parent_id ?? '__none__'
      if (!map.has(gid)) {
        map.set(gid, { name: item.parent_name ?? 'Other', total: 0, colorIdx: colorIdx++, children: [] })
      }
      const g = map.get(gid)!
      g.total += Number(item.total)
      g.children.push({
        name: item.name,
        id: item.id,
        parent_id: item.parent_id,
        parent_name: item.parent_name,
        size: Number(item.total),
        pct: item.pct,
        fill: chartColor(colorIdx),
      })
    }
    return map
  }, [items])

  // groupBy=group → show only top-level groups (no drill-down)
  // groupBy=category → show all categories flat (colored by group)
  // groupBy=payee → fall back to category (payee data not in this endpoint)
  const visibleItems: TreeNode[] = useMemo(() => {
    if (groupBy === 'category') {
      // flat: all categories colored by their group
      return items.map((item) => {
        const gid = item.parent_id ?? '__none__'
        const colorIdx = [...groups.keys()].indexOf(gid)
        return {
          name: item.name,
          id: item.id,
          parent_id: item.parent_id,
          parent_name: item.parent_name,
          size: Number(item.total),
          pct: item.pct,
          fill: chartColor(colorIdx),
        }
      })
    }
    // group (or payee fallback) → group-level boxes, or the selected group's
    // categories once drilled (category mode already returned above)
    if (selectedGroup) {
      return groups.get(selectedGroup)?.children ?? []
    }
    return [...groups.values()].map((g, i) => ({
      name: g.name,
      id: g.name,
      parent_id: null,
      parent_name: null,
      size: g.total,
      pct: grandTotal > 0 ? (g.total / grandTotal) * 100 : 0,
      fill: chartColor(i),
    }))
  }, [groupBy, selectedGroup, groups, items, grandTotal])

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState onRetry={() => refetch()} />

  const selectedGroupName = selectedGroup ? groups.get(selectedGroup)?.name : null

  return (
    <div className="report-section">
      <div className="report-section__header">
        <h2 className="report-section__title">Spending Treemap</h2>
        <ReportInfoButton title="Spending Treemap">
          <p>Each rectangle represents a spending bucket — <strong>size is proportional to amount spent</strong>.</p>
          <p><strong>Group</strong> mode: shows category groups only. <strong>Category</strong> mode: shows all categories flat, colored by group. Use the global <em>Group by</em> filter to switch. In Group mode you can click a tile to drill into its categories.</p>
          <p>Clicking a category tile opens the list of transactions behind it below the chart.</p>
        </ReportInfoButton>
        {groupBy !== 'category' && (
          <div className="treemap-breadcrumb">
            <button className="treemap-crumb" onClick={() => setSelectedGroup(null)}>
              All Groups
            </button>
            {selectedGroupName && (
              <>
                <ChevronRight size={14} className="treemap-crumb-sep" />
                <span className="treemap-crumb treemap-crumb--active">{selectedGroupName}</span>
              </>
            )}
          </div>
        )}
        <label className="report-toggle">
          <input
            type="checkbox"
            checked={hideSavings}
            onChange={(e) => setHideSavings(e.target.checked)}
          />
          Hide tagged as savings
        </label>
        <div className="ms-auto">
          <ReportExportButton
            reportId="treemap"
            getRows={() =>
              items.map((item) => ({
                category: item.name,
                group: item.parent_name ?? '',
                total: Number(item.total),
                pct: item.pct,
                count: item.count,
              }))
            }
            captureRef={captureRef}
            window={{ start: filters.startDate, end: filters.endDate }}
          />
        </div>
      </div>
      <p className="report-section__subtitle">
        {groupBy === 'category'
          ? 'All categories shown flat, colored by group. Click a tile to see its transactions.'
          : selectedGroup
            ? 'Showing categories in selected group. Click a tile to see its transactions.'
            : 'Click a group to drill down into its categories.'}
      </p>

      {visibleItems.length === 0 ? (
        <div className="reports-empty">No spending data for this period.</div>
      ) : (
        <div ref={captureRef} className="report-capture">
        <ResponsiveContainer width="100%" height={chartHeight}>
          <Treemap
            data={visibleItems}
            dataKey="size"
            aspectRatio={4 / 3}
            stroke="var(--bg-primary)"
            isAnimationActive={false}
            content={<TreemapContent />}
            onClick={(node) => {
              if (groupBy !== 'category' && !selectedGroup) {
                const gid = [...groups.entries()].find(([, g]) => g.name === node.name)?.[0]
                if (gid) setSelectedGroup(gid)
                return
              }
              // Category tiles (flat mode, or drilled into a group) open the
              // transaction panel below the chart
              const item = visibleItems.find((i) => i.name === node.name)
              if (item?.id) {
                setDrillDown({
                  kind: 'category',
                  label: item.name,
                  scope: 'leaf',
                  direction: 'outflow',
                  categoryIds: [item.id],
                  startDate: filters.startDate,
                  endDate: filters.endDate,
                })
              }
            }}
          >
            <Tooltip
              offset={16}
              isAnimationActive={false}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const p = payload[0]?.payload
                return (
                  <div className="chart-tooltip">
                    <div className="chart-tooltip__label">{p?.name}</div>
                    <div className="chart-tooltip__row">
                      <span className="chart-tooltip__name">Amount</span>
                      <span className="chart-tooltip__value">{formatMoney(p?.size ?? 0)}</span>
                    </div>
                    <div className="chart-tooltip__row">
                      <span className="chart-tooltip__name">Share</span>
                      <span className="chart-tooltip__value">{(p?.pct ?? 0).toFixed(1)}%</span>
                    </div>
                  </div>
                )
              }}
            />
          </Treemap>
        </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

function TreemapContent(props: { x?: number; y?: number; width?: number; height?: number; name?: string; size?: number; fill?: string }) {
  const { formatMoney } = useFormatters()
  const { x = 0, y = 0, width = 0, height = 0, name = '', size = 0, fill = 'var(--chart-1)' } = props
  if (width < 30 || height < 20) return <g><rect x={x} y={y} width={width} height={height} fill={fill} /></g>
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} fill={fill} fillOpacity={0.85} rx={3} />
      {height > 30 && (
        <text x={x + width / 2} y={y + height / 2 - 6} textAnchor="middle" fontSize={Math.min(12, width / 7)} fill="var(--heatmap-cell-text)" fontWeight={600}>
          {name.length > Math.floor(width / 7) ? name.slice(0, Math.floor(width / 7) - 1) + '…' : name}
        </text>
      )}
      {height > 48 && (
        <text x={x + width / 2} y={y + height / 2 + 10} textAnchor="middle" fontSize={10} fill="var(--heatmap-cell-text)" fillOpacity={0.75}>
          {formatMoney(size)}
        </text>
      )}
    </g>
  )
}
