/** Pure view-model math for the cash-flow sankey: drill-level node/link
 * assembly and period-over-period deltas. Extracted from CashFlowSankey so
 * the money math is unit-testable. */
import type { CashFlowReport, CategoryPayee } from '../../../types'

export interface SankeyViewNode {
  name: string
  type: string
  id: string
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
  groups: Map<string, number>
  cats: Map<string, number>
}

/** Signed delta as "+$123 (+12%)"; pct omitted when prev is 0. */
export function formatDelta(
  current: number,
  prev: number,
  formatMoney: (n: number) => string,
): string {
  const delta = current - prev
  const sign = delta >= 0 ? '+' : '−'
  const amount = `${sign}${formatMoney(Math.abs(delta))}`
  if (prev === 0) return amount
  return `${amount} (${sign}${Math.abs((delta / prev) * 100).toFixed(0)}%)`
}

/** For income more is good; for expense-side nodes more is bad. */
export function deltaColor(current: number, prev: number, type: string): string {
  const increased = current >= prev
  const good = type === 'income' ? increased : !increased
  return good ? 'var(--color-positive)' : 'var(--color-negative)'
}

/** Previous-window totals keyed by the backend's stable node ids (g_/c_...),
 * so deltas survive drilling. */
export function extractPrevTotals(prevData: CashFlowReport): PrevTotals {
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
}

/** Build the drill-level view: Income → Groups → Categories → Payees.
 * Zero-value links are dropped; prev values attach when prevTotals given
 * (payees match by name — they have no stable ids at level 3). */
export function buildSankeyView(
  data: CashFlowReport | undefined,
  selectedGroupId: string | null,
  selectedCategoryId: string | null,
  prevTotals: PrevTotals | null,
  prevData: CashFlowReport | undefined,
): SankeyView {
  if (!data || data.nodes.length === 0) {
    return {
      sankeyData: { nodes: [], links: [] },
      groupCategories: {},
      categoryPayees: {},
    }
  }

  const groups = data.nodes.filter((n) => n.type === 'category_group')
  const categories = data.nodes.filter((n) => n.type === 'category')

  const groupTotals = new Map<string, number>()
  for (const link of data.links) {
    if (link.source === '__budget__') {
      groupTotals.set(link.target, Number(link.value))
    }
  }

  const catTotals = new Map<string, number>()
  for (const link of data.links) {
    const sourceNode = data.nodes.find((n) => n.id === link.source)
    if (sourceNode?.type === 'category_group') {
      catTotals.set(link.target, Number(link.value))
    }
  }

  const nodes: SankeyViewNode[] = []
  const links: SankeyViewLink[] = []

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
          (prevData?.category_payees[selectedCategoryId] ?? []).map((p) => [
            p.name,
            Number(p.total),
          ]),
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
}
