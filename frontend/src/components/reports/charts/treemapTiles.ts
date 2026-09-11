/**
 * The Spending Treemap's tiles, and which colour each one wears. Pure, so
 * "a category tile wears its group's colour" is a test instead of something
 * you have to click through a chart to notice.
 *
 * A group's colour is ONE field, `TreemapGroup.colorIdx`, read by every tile
 * that shows the group or a category in it. There were three spellings — the
 * running counter for children, `indexOf(gid)` over the map's keys for flat
 * mode, and the map position for group tiles — which agreed only while the
 * map's insertion order matched the counter, and the first of them was
 * already wrong.
 */
import type { SpendingGroupItem } from '../../../types'
import { chartColor } from './chartColors'
import { truncateLabel } from '../../../utils/truncateLabel'
import { shareOfTotal } from '../drillDownTotals'

export interface TreeNode {
  name: string
  id: string
  parent_id: string | null
  parent_name: string | null
  size: number
  /** Share of the grand total; null when there is no positive total to be
   *  a share of (see `shareOfTotal`). */
  pct: number | null
  fill?: string
  // Recharts' Treemap data points must satisfy TreemapDataType's index signature.
  [key: string]: unknown
}

export interface TreemapGroup {
  name: string
  total: number
  /** This group's colour slot — the only place it is decided. */
  colorIdx: number
  children: TreeNode[]
}

type Item = Pick<SpendingGroupItem, 'id' | 'name' | 'parent_id' | 'parent_name' | 'total' | 'pct'>

const groupKey = (item: Item) => item.parent_id ?? '__none__'

function categoryTile(item: Item, group: TreemapGroup): TreeNode {
  return {
    name: item.name,
    id: item.id,
    parent_id: item.parent_id,
    parent_name: item.parent_name,
    size: item.total,
    pct: item.pct,
    fill: chartColor(group.colorIdx),
  }
}

/** Categories bucketed by group, each group given the next colour slot. */
export function treemapGroups(items: readonly Item[]): Map<string, TreemapGroup> {
  const map = new Map<string, TreemapGroup>()
  for (const item of items) {
    const gid = groupKey(item)
    let g = map.get(gid)
    if (!g) {
      g = { name: item.parent_name ?? 'Other', total: 0, colorIdx: map.size, children: [] }
      map.set(gid, g)
    }
    g.total += item.total
    g.children.push(categoryTile(item, g))
  }
  return map
}

/** Category mode: every category flat, coloured by its group. */
export function flatTiles(
  items: readonly Item[],
  groups: ReadonlyMap<string, TreemapGroup>
): TreeNode[] {
  return items.map((item) => categoryTile(item, groups.get(groupKey(item))!))
}

/** Group mode, undrilled: one tile per group. */
export function groupTiles(
  groups: ReadonlyMap<string, TreemapGroup>,
  grandTotal: number
): TreeNode[] {
  return [...groups.values()].map((g) => ({
    name: g.name,
    id: g.name,
    parent_id: null,
    parent_name: null,
    size: g.total,
    pct: shareOfTotal(g.total, grandTotal),
    fill: chartColor(g.colorIdx),
  }))
}

// A tile's name label. Pure because recharts renders the tile at zero size
// under jsdom.

/** Horizontal pixels one label character is given — the font shrinks with a
 * narrow tile by the same measure the label is cut by. */
const PX_PER_CHAR = 7

/** The label's font size: 12px, smaller on a tile too narrow for it. */
export function tileFontSize(width: number): number {
  return Math.min(12, width / PX_PER_CHAR)
}

/** The name, cut to what fits across the tile by the rule every chart shares.
 * The tile once sliced its own (`floor(width / 7) - 1`), one character wider
 * than every chart at the same limit. */
export function tileLabel(name: string, width: number): string {
  return truncateLabel(name, Math.floor(width / PX_PER_CHAR))
}
