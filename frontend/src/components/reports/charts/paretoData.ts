/** Pure math for the Pareto report: sorting/aggregation per group-by mode,
 * cumulative percentages, and the 80%-line insight. Extracted from
 * ParetoChart so the concentration math is unit-testable. */
import type { GroupBy } from '../../../stores/reportStore'

export interface ParetoItem {
  id: string
  name: string
  total: number
  groupKey: string | null
  groupName: string | null
}

interface SpendingGroupItemLike {
  id: string
  name: string
  total: string | number
  parent_id: string | null
  parent_name: string | null
}

interface PayeeItemLike {
  payee_id: string
  payee_name: string
  total: string | number
}

/** Sort + (for group mode) aggregate the raw report items, largest first.
 * Category mode trusts the backend total; payee/group totals are sums of
 * the visible items. */
export function buildParetoItems(
  groupBy: GroupBy,
  spendingItems: SpendingGroupItemLike[],
  payeeItems: PayeeItemLike[],
  backendTotal: string | number | undefined,
): { sorted: ParetoItem[]; grandTotal: number } {
  if (groupBy === 'payee') {
    const items = [...payeeItems].sort((a, b) => Number(b.total) - Number(a.total))
    const total = items.reduce((s, p) => s + Number(p.total), 0)
    return {
      sorted: items.map((p) => ({
        id: p.payee_id,
        name: p.payee_name,
        total: Number(p.total),
        groupKey: null,
        groupName: null,
      })),
      grandTotal: total,
    }
  }
  if (groupBy === 'group') {
    const map = new Map<string, { id: string; name: string; total: number }>()
    for (const item of spendingItems) {
      const gid = item.parent_id ?? '__none__'
      const ex = map.get(gid)
      if (ex) {
        ex.total += Number(item.total)
      } else {
        map.set(gid, {
          id: gid,
          name: item.parent_name ?? 'Uncategorized',
          total: Number(item.total),
        })
      }
    }
    const items = [...map.values()].sort((a, b) => b.total - a.total)
    const total = items.reduce((s, i) => s + i.total, 0)
    return {
      sorted: items.map((i) => ({ ...i, groupKey: i.id, groupName: null })),
      grandTotal: total,
    }
  }
  const items = [...spendingItems].sort((a, b) => Number(b.total) - Number(a.total))
  return {
    sorted: items.map((i) => ({
      id: i.id,
      name: i.name,
      total: Number(i.total),
      groupKey: i.parent_id,
      groupName: i.parent_name,
    })),
    grandTotal: Number(backendTotal ?? 0),
  }
}

/** Running share of the grand total for each item, in order (0–100). */
export function cumulativePercents(items: ParetoItem[], grandTotal: number): number[] {
  const cumulative = items.reduce<number[]>(
    (acc, item) => [...acc, (acc[acc.length - 1] ?? 0) + item.total],
    [],
  )
  return cumulative.map((c) => (grandTotal > 0 ? (c / grandTotal) * 100 : 0))
}

/** The 80/20 insight: index of the item whose cumulative share reaches 80%,
 * and what fraction of ALL items that prefix represents. */
export function paretoInsight(
  cumulativePcts: number[],
  totalItemCount: number,
): { idx80: number; pct80coverage: string | null } {
  const idx80 = cumulativePcts.findIndex((pct) => pct >= 80)
  const pct80coverage =
    idx80 >= 0 && totalItemCount > 0
      ? (((idx80 + 1) / totalItemCount) * 100).toFixed(0)
      : null
  return { idx80, pct80coverage }
}

/** Share of the grand total for one item (0–100). */
export function shareOfTotal(total: number, grandTotal: number): number {
  return grandTotal > 0 ? (total / grandTotal) * 100 : 0
}
