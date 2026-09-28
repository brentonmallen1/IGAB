import { useMemo, useState } from 'react'
import { ResponsiveContainer, Tooltip, Treemap } from 'recharts'
import type { SpendingGroupItem } from '../../../types'
import { useChartHeight } from '../../../hooks/useChartHeight'
import { useFormatters } from '../../../hooks/useFormatters'
import { ChartLegend } from './ChartLegend'
import {
  drawableTiles,
  flatTiles,
  groupColorKey,
  groupTiles,
  isTile,
  tileFontSize,
  tileLabel,
  treemapGroups,
  type TreeNode,
} from './treemapTiles'

interface Props {
  items: readonly SpendingGroupItem[]
  /** What the tiles' shares are of in an undrilled view: the served total. */
  total: number
  mode: 'group' | 'category'
  /** The group opened from the table or a tile — shared with the table, so
   *  switching view keeps what you were looking at. */
  openGroup: string | null
  onOpenGroup: (key: string) => void
  onOpenCategory: (tile: TreeNode) => void
}

/**
 * Where it went's rows as areas: the same served rows the table ranks, never
 * a second query. Group mode draws one tile per group and opens a group into
 * its categories; category mode draws every category, shaded by its group,
 * with a key.
 */
export function WhereItWentTreemap({
  items,
  total,
  mode,
  openGroup,
  onOpenGroup,
  onOpenCategory,
}: Props) {
  const chartHeight = useChartHeight(440)
  const { formatMoney } = useFormatters()
  const [highlight, setHighlight] = useState<string | null>(null)
  const groups = useMemo(() => treemapGroups(items), [items])

  const { drawn, undrawn } = useMemo(() => {
    if (mode === 'category') return drawableTiles(flatTiles(items, groups, total))
    if (openGroup) return drawableTiles(groups.get(openGroup)?.children ?? [])
    return drawableTiles(groupTiles(groups, total))
  }, [mode, openGroup, groups, items, total])
  const colorKey = useMemo(() => groupColorKey(groups), [groups])
  // Pointing at a group in the key fades every other group's tiles, which is
  // what tells two groups apart once the palette repeats.
  const shown = useMemo(
    () => drawn.map((t) => ({ ...t, dimmed: !!highlight && t.groupKey !== highlight })),
    [drawn, highlight]
  )
  const groupTilesShown = mode === 'group' && !openGroup

  return (
    <>
      <div className="report-chart" style={{ height: chartHeight }}>
        <ResponsiveContainer width="100%" height="100%">
          <Treemap
            data={shown}
            dataKey="size"
            aspectRatio={4 / 3}
            stroke="var(--bg-primary)"
            isAnimationActive={false}
            content={<TreemapTile />}
            onClick={(node) => {
              // By key and id, never by name: the old treemap found the
              // clicked group by its name, so of two groups called "Bills"
              // the second could never be opened.
              const tile = node as unknown as TreeNode
              if (groupTilesShown) onOpenGroup(tile.groupKey)
              else onOpenCategory(tile)
            }}
          >
            <Tooltip
              offset={16}
              isAnimationActive={false}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const p = payload[0]?.payload as TreeNode | undefined
                return (
                  <div className="chart-tooltip">
                    <div className="chart-tooltip__label">{p?.name}</div>
                    <div className="chart-tooltip__row">
                      <span className="chart-tooltip__name">Spent</span>
                      <span className="chart-tooltip__value">{formatMoney(p?.size ?? 0)}</span>
                    </div>
                    <div className="chart-tooltip__row">
                      <span className="chart-tooltip__name">Share</span>
                      <span className="chart-tooltip__value">
                        {p?.pct == null ? '—' : `${p.pct.toFixed(1)}%`}
                      </span>
                    </div>
                  </div>
                )
              }}
            />
          </Treemap>
        </ResponsiveContainer>
      </div>
      {mode === 'category' && (
        <ChartLegend series={colorKey} active={highlight} onHover={setHighlight} />
      )}
      {undrawn > 0 && (
        <p className="report-section__subtitle">
          Refunds outweighed spending on {undrawn} {undrawn === 1 ? 'line' : 'lines'}, so{' '}
          {undrawn === 1 ? 'it has' : 'they have'} no area to draw; the table lists{' '}
          {undrawn === 1 ? 'it' : 'them'} and the total counts {undrawn === 1 ? 'it' : 'them'}.
        </p>
      )}
    </>
  )
}

export function TreemapTile(props: {
  x?: number
  y?: number
  width?: number
  height?: number
  depth?: number
  name?: string
  size?: number
  fill?: string
  dimmed?: boolean
}) {
  const { formatMoney } = useFormatters()
  if (!isTile(props)) return null
  const {
    x = 0,
    y = 0,
    width = 0,
    height = 0,
    name = '',
    size = 0,
    fill = 'var(--chart-1)',
    dimmed = false,
  } = props
  const opacity = dimmed ? 0.25 : 0.85
  if (width < 30 || height < 20)
    return (
      <g>
        <rect x={x} y={y} width={width} height={height} fill={fill} fillOpacity={opacity} />
      </g>
    )
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} fill={fill} fillOpacity={opacity} rx={3} />
      {height > 30 && (
        <text
          x={x + width / 2}
          y={y + height / 2 - 6}
          textAnchor="middle"
          fontSize={tileFontSize(width)}
          fill="var(--heatmap-cell-text)"
          fontWeight={600}
        >
          {tileLabel(name, width)}
        </text>
      )}
      {height > 48 && (
        <text
          x={x + width / 2}
          y={y + height / 2 + 10}
          textAnchor="middle"
          fontSize={10}
          fill="var(--heatmap-cell-text)"
          fillOpacity={0.75}
        >
          {formatMoney(size)}
        </text>
      )}
    </g>
  )
}
