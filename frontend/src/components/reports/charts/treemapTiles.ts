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
import { categoryKey } from '../drillScope'

export interface TreeNode {
  name: string
  id: string
  /** The category a tile opens: its id, or null for the Uncategorized line
   *  (`categoryTarget`). Null on a group tile too, which opens its group. */
  categoryId: string | null
  parent_id: string | null
  parent_name: string | null
  /** The group whose colour the tile wears — what the colour key names. */
  groupName: string
  size: number
  /** Share of what is on screen — the whole period, or the group drilled
   *  into — as the Breakdown states it. Null when there is no positive total
   *  to be a share of (see `shareOfTotal`). */
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

type Item = Pick<SpendingGroupItem, 'id' | 'name' | 'parent_id' | 'parent_name' | 'total'>

const groupKey = (item: Item) => item.parent_id ?? '__none__'

function categoryTile(item: Item, group: TreemapGroup, shownTotal: number): TreeNode {
  return {
    name: item.name,
    id: categoryKey(item.id),
    categoryId: item.id,
    parent_id: item.parent_id,
    parent_name: item.parent_name,
    groupName: group.name,
    size: item.total,
    pct: shareOfTotal(item.total, shownTotal),
    fill: chartColor(group.colorIdx),
  }
}

/** Categories bucketed by group, each group given the next colour slot. A
 *  group's children state their share of the group — what is on screen once
 *  it is drilled into. The tile used to state its share of the whole period
 *  there, beside a Breakdown that said "of what is on screen". */
export function treemapGroups(items: readonly Item[]): Map<string, TreemapGroup> {
  const map = new Map<string, TreemapGroup>()
  const members = new Map<string, Item[]>()
  for (const item of items) {
    const gid = groupKey(item)
    let g = map.get(gid)
    if (!g) {
      g = { name: item.parent_name, total: 0, colorIdx: map.size, children: [] }
      map.set(gid, g)
      members.set(gid, [])
    }
    g.total += item.total
    members.get(gid)!.push(item)
  }
  for (const [gid, g] of map) {
    g.children = members.get(gid)!.map((item) => categoryTile(item, g, g.total))
  }
  return map
}

/** Category mode: every category flat, coloured by its group, each a share
 *  of the whole period. */
export function flatTiles(
  items: readonly Item[],
  groups: ReadonlyMap<string, TreemapGroup>,
  grandTotal: number
): TreeNode[] {
  return items.map((item) => categoryTile(item, groups.get(groupKey(item))!, grandTotal))
}

/** What a treemap can draw: a tile's area is its spending, so a line that
 *  took back more in refunds than it spent — net negative, or nothing at
 *  all — has no area. It stays in the report's total; the page says how
 *  many it left off. */
export function drawableTiles(tiles: readonly TreeNode[]): {
  drawn: TreeNode[]
  undrawn: number
} {
  const drawn = tiles.filter((t) => t.size > 0)
  return { drawn, undrawn: tiles.length - drawn.length }
}

/** The key to category mode's colours: each group once, in slot order. A
 *  flat treemap shades every category by its group and named none of them. */
export function groupColorKey(groups: ReadonlyMap<string, TreemapGroup>) {
  return [...groups.values()].map((g) => ({ name: g.name, color: chartColor(g.colorIdx) }))
}

/** Group mode, undrilled: one tile per group. */
export function groupTiles(
  groups: ReadonlyMap<string, TreemapGroup>,
  grandTotal: number
): TreeNode[] {
  return [...groups.values()].map((g) => ({
    name: g.name,
    id: g.name,
    categoryId: null,
    parent_id: null,
    parent_name: null,
    groupName: g.name,
    size: g.total,
    pct: shareOfTotal(g.total, grandTotal),
    fill: chartColor(g.colorIdx),
  }))
}

/** Whether a node recharts hands the content renderer is a tile to draw.
 *
 *  Treemap renders the tree's root through the same renderer as its tiles:
 *  depth 0, the whole chart's area, no name and no `size`. Drawn, it put a
 *  stray "$0.00" at the centre of the chart on every render. */
export function isTile(node: { depth?: number; name?: string }): boolean {
  return (node.depth ?? 0) > 0 && Boolean(node.name)
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
