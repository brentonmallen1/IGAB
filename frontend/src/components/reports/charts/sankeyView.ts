/** Pure view-model math for the cash-flow sankey: drill-level node/link
 * assembly, period-over-period deltas, geometry and the export. Extracted
 * from CashFlowSankey so it is unit-testable.
 *
 * Every figure is the server's (`domain/cash_flow.py`): the sources, the hub
 * and the balancing Left over / Shortfall node are all served links. This
 * module only picks which of them a drill level shows. */
import type { CashFlowReport, CategoryPayee } from '../../../types'
import type { DrillDownContext } from '../../../stores/reportStore'
import { categoryTarget } from '../drillScope'

/** The served hub every source flows into and every group flows out of. */
export const HUB = '__budget__'

export interface SankeyViewNode {
  name: string
  type: string
  id: string
  /** The entity the node stands for. `id` is a display key that may compose
   *  several ids, so a drill-down must read this rather than parse that. */
  entity_id?: string | null
  /** The activity classes a category node counted — served, see `SankeyNode`. */
  activity_classes?: string[] | null
  /** Previous-window value when compare is on; null = node is new this window */
  prev?: number | null
}

export interface SankeyViewLink {
  source: number
  target: number
  value: number
}

export interface SankeyView {
  sankeyData: { nodes: SankeyViewNode[]; links: SankeyViewLink[] }
  groupCategories: Record<string, CategoryPayee[]>
  categoryPayees: Record<string, CategoryPayee[]>
}

export interface PrevTotals {
  sources: Map<string, number>
  groups: Map<string, number>
  cats: Map<string, number>
}

/** Signed delta as "+$123 (+12%)"; pct omitted when prev is 0.
 *
 * Masked, it is `formatMoney`'s mask alone: the sign and the percentage both
 * went outside it ("−$•••• (−30%)"), which says which way spending moved and
 * by how much while every other figure on the page reads "$••••". The colour
 * beside it stays — privacy mode masks figures, not state. Required, so a
 * caller cannot leak the sign by leaving it out. */
export function formatDelta(
  current: number,
  prev: number,
  formatMoney: (n: number) => string,
  masked: boolean
): string {
  const delta = current - prev
  if (masked) return formatMoney(Math.abs(delta))
  const sign = delta >= 0 ? '+' : '−'
  const amount = `${sign}${formatMoney(Math.abs(delta))}`
  if (prev === 0) return amount
  return `${amount} (${sign}${Math.abs((delta / prev) * 100).toFixed(0)}%)`
}

/** Nodes where more is good news: an income source, and what was left over.
 *  Everything else — spending, a shortfall, borrowing — reads the other way. */
const MORE_IS_GOOD = new Set(['income', 'income_payee', 'left_over'])

export function deltaColor(current: number, prev: number, type: string): string {
  const increased = current >= prev
  const good = MORE_IS_GOOD.has(type) ? increased : !increased
  return good ? 'var(--color-positive)' : 'var(--color-negative)'
}

/** Previous-window totals keyed by the backend's stable node ids, so deltas
 * survive drilling: sources by the link into the hub, groups by the link out
 * of it, categories by the link out of their group. */
export function extractPrevTotals(prevData: CashFlowReport): PrevTotals {
  const sources = new Map<string, number>()
  const groups = new Map<string, number>()
  const cats = new Map<string, number>()
  const nodeType = new Map(prevData.nodes.map((n) => [n.id, n.type]))
  for (const link of prevData.links) {
    if (link.target === HUB) sources.set(link.source, link.value)
    else if (link.source === HUB) groups.set(link.target, link.value)
    else if (nodeType.get(link.source) === 'category_group') cats.set(link.target, link.value)
  }
  return { sources, groups, cats }
}

/** The name the hub goes by at a drill level: at the top it is what came in
 *  (Budget); drilled, it stands for the group's share of it. */
const HUB_NAME = 'Budget'

/** Build the drill-level view.
 *
 *  - Top: every source → Budget → every group, Left over included. The client
 *    drew ONE "Income" node here, sized to the outflows rather than the
 *    income it was named for — twice the month's income in the window that
 *    surfaced it — and threw the served sources away.
 *  - A group: Budget → group → its categories.
 *  - A category: Budget → group → category → payees, plus what came back
 *    (`category_returns`) as a source into the category, so a category whose
 *    refunds came from a payee with no charge still balances.
 *
 * Zero-value links are dropped; prev values attach when prevTotals is given
 * (payees match by name — they have no stable ids at level 3). */
export function buildSankeyView(
  data: CashFlowReport | undefined,
  selectedGroupId: string | null,
  selectedCategoryId: string | null,
  prevTotals: PrevTotals | null,
  prevData: CashFlowReport | undefined
): SankeyView {
  if (!data || data.nodes.length === 0) {
    return {
      sankeyData: { nodes: [], links: [] },
      groupCategories: {},
      categoryPayees: {},
    }
  }

  const byId = new Map(data.nodes.map((n) => [n.id, n]))
  const into = data.links.filter((l) => l.target === HUB)
  const outOf = data.links.filter((l) => l.source === HUB)
  const groupTotal = new Map(outOf.map((l) => [l.target, l.value]))
  const catTotal = new Map(
    data.links
      .filter((l) => byId.get(l.source)?.type === 'category_group')
      .map((l) => [l.target, l.value])
  )

  const nodes: SankeyViewNode[] = []
  const links: SankeyViewLink[] = []
  const add = (id: string, fallbackName = id): number => {
    const served = byId.get(id)
    nodes.push({
      id,
      name: served?.name ?? fallbackName,
      type: served?.type ?? 'budget',
      entity_id: served?.entity_id,
      activity_classes: served?.activity_classes,
    })
    return nodes.length - 1
  }

  const group = selectedGroupId ? byId.get(selectedGroupId) : undefined
  const category = selectedCategoryId ? byId.get(selectedCategoryId) : undefined

  if (group && category) {
    const hub = add(HUB, HUB_NAME)
    const g = add(group.id)
    const c = add(category.id)
    links.push({ source: hub, target: g, value: groupTotal.get(group.id) ?? 0 })
    links.push({ source: g, target: c, value: catTotal.get(category.id) ?? 0 })
    const back = data.category_returns?.[category.id]
    if (back) {
      nodes.push({ id: `${category.id}__returns`, name: back.name, type: 'inflow' })
      links.push({ source: nodes.length - 1, target: c, value: back.total })
    }
    ;(data.category_payees[category.id] ?? []).forEach((payee, i) => {
      nodes.push({ id: `payee_${i}`, name: payee.name, type: 'payee' })
      links.push({ source: c, target: nodes.length - 1, value: payee.total })
    })
  } else if (group) {
    const hub = add(HUB, HUB_NAME)
    const g = add(group.id)
    links.push({ source: hub, target: g, value: groupTotal.get(group.id) ?? 0 })
    for (const l of data.links) {
      if (l.source !== group.id) continue
      links.push({ source: g, target: add(l.target), value: l.value })
    }
  } else {
    for (const l of into) add(l.source)
    const hub = add(HUB, HUB_NAME)
    into.forEach((l, i) => links.push({ source: i, target: hub, value: l.value }))
    for (const l of outOf) links.push({ source: hub, target: add(l.target), value: l.value })
  }

  // Attach previous-window values for the compare overlay. null = new node.
  if (prevTotals) {
    const prevPayees = selectedCategoryId
      ? new Map((prevData?.category_payees[selectedCategoryId] ?? []).map((p) => [p.name, p.total]))
      : null
    const sourceIds = new Set(into.map((l) => l.source))
    // The hub and a category's returns carry no delta: the hub is the sum of
    // either side, whose deltas are on the cards.
    for (const node of nodes) {
      if (node.type === 'category') node.prev = prevTotals.cats.get(node.id) ?? null
      else if (node.type === 'payee') node.prev = prevPayees?.get(node.name) ?? null
      else if (node.type === 'category_group' || node.type === 'left_over')
        node.prev = prevTotals.groups.get(node.id) ?? null
      else if (sourceIds.has(node.id)) node.prev = prevTotals.sources.get(node.id) ?? null
    }
  }

  return {
    sankeyData: { nodes, links: links.filter((l) => l.value > 0) },
    groupCategories: data.group_categories ?? {},
    categoryPayees: data.category_payees ?? {},
  }
}

/** The chart's side margins and how many characters a label may take, from
 *  the width it is drawn at. Fixed margins of 100 and 200 left a phone about
 *  ninety pixels of diagram between them; proportional ones keep the bands
 *  and the labels both legible. Labels sit in the margins — first column to
 *  the left of its nodes, every other column to the right — so a label's
 *  budget is its margin at the label font's average glyph width. */
export function sankeyGeometry(width: number): { left: number; right: number; labelChars: number } {
  const clamp = (v: number, lo: number, hi: number) => Math.round(Math.min(hi, Math.max(lo, v)))
  const left = clamp(width * 0.22, 72, 170)
  const right = clamp(width * 0.24, 80, 190)
  return { left, right, labelChars: Math.max(8, Math.floor((Math.min(left, right) - 10) / 6.5)) }
}

/** The gap between nodes in a column: room for a node's label block — name
 *  and amount, and the delta line under them when comparing — so the labels
 *  of two thin neighbours do not print over each other. */
export function sankeyNodePadding(compare: boolean): number {
  return compare ? 40 : 28
}

/** The chart's height: `base`, or taller when a column holds more nodes than
 *  `base` can space at `sankeyNodePadding` — fifteen groups in 500px put the
 *  small ones' labels on top of one another. */
export function sankeyHeight(
  data: { nodes: readonly unknown[]; links: readonly SankeyViewLink[] },
  base: number,
  compare: boolean
): number {
  const depth = new Array<number>(data.nodes.length).fill(0)
  // Longest path from a source, as the layout assigns columns; links run
  // left to right, so a few relaxation passes settle it.
  for (let pass = 0; pass < data.nodes.length; pass++) {
    let moved = false
    for (const l of data.links) {
      if (depth[l.target] < depth[l.source] + 1) {
        depth[l.target] = depth[l.source] + 1
        moved = true
      }
    }
    if (!moved) break
  }
  const perColumn = new Map<number, number>()
  for (const d of depth) perColumn.set(d, (perColumn.get(d) ?? 0) + 1)
  const tallest = Math.max(0, ...perColumn.values())
  return Math.max(base, tallest * (sankeyNodePadding(compare) + 12) + 24)
}

/** The export: every link named, then totals. The income links (sources
 *  named `inc_…`) add up to the TOTAL income row — the server draws the
 *  sources past the fifteenth as one "Other income" node; it used to drop
 *  them, and the export's income links summed short of its own total. */
export function sankeyExportRows(data: CashFlowReport): Record<string, unknown>[] {
  const nodeName = new Map(data.nodes.map((n) => [n.id, n.name]))
  const rows: Record<string, unknown>[] = data.links.map((l) => ({
    source: nodeName.get(l.source) ?? l.source,
    target: nodeName.get(l.target) ?? l.target,
    value: l.value,
  }))
  const sum = (pick: (l: CashFlowReport['links'][number]) => boolean) =>
    data.links.filter(pick).reduce((s, l) => s + Number(l.value), 0)
  rows.push({ source: 'TOTAL', target: 'income', value: data.total_income })
  rows.push({ source: 'TOTAL', target: 'money in', value: sum((l) => l.target === HUB) })
  rows.push({ source: 'TOTAL', target: 'money out', value: sum((l) => l.source === HUB) })
  if (data.net !== null) rows.push({ source: 'TOTAL', target: 'net', value: data.net })
  if (data.total_assigned !== null)
    rows.push({ source: 'TOTAL', target: 'assigned', value: data.total_assigned })
  return rows
}

/**
 * The drill-down a category node opens: exactly the rows it counted.
 *
 * `entity_id` scopes a real category; a null one is a pseudo-category — the
 * Savings and Debt payments trunks and the Uncategorized bucket — scoped by
 * the absence of a category. Those three share that and differ ONLY by class,
 * so without the node's served `activity_classes` each opened the union of
 * all three: a $500 Savings node listing $1,580. A real category sitting
 * under both its own group and the savings trunk is two nodes that differ
 * the same way. The classes are served rather than inferred from the node id
 * because the client is missing the input: it cannot know which classes an
 * Uncategorized bucket happened to hold.
 *
 * Both directions: the node is net of refunds, so the list that explains it
 * holds the refunds too. An outflow-only drill totalled more than the node.
 */
export function categoryNodeDrill(
  node: Pick<SankeyViewNode, 'name' | 'entity_id' | 'activity_classes'>,
  window: { startDate: string; endDate: string }
): DrillDownContext {
  return {
    kind: 'category',
    label: node.name,
    scope: 'leaf',
    // `categoryTarget`, the rule every spending chart opens a line by.
    ...categoryTarget([node.entity_id ?? null]),
    activityClasses: node.activity_classes ?? undefined,
    ...window,
  }
}
