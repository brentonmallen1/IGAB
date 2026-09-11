/** Pure math for the Pareto report: sorting/aggregation per group-by mode,
 * cumulative percentages, and the 80%-line insight. Extracted from
 * ParetoChart so the concentration math is unit-testable. */
import type { GroupBy } from '../../../stores/reportStore'
import { shareOfTotal } from '../drillDownTotals'

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

/** The payee analysis response, whole: the ranked rows travel with the
 *  served figures that span every payee, so a caller cannot pass one without
 *  the other. */
interface PayeeReportLike {
  payees: PayeeItemLike[]
  total: string | number
  payee_count: number
  payees_to_80pct: number | null
}

/** Sort + (for group mode) aggregate the raw report items, largest first.
 *
 * Category and payee mode trust the server's total, which spans everything;
 * group totals are summed from the categories, which the same response
 * carries in full. `universeCount` is how many things exist in the window —
 * larger than `sorted.length` only in payee mode, where the server ranks the
 * top 25 and the report used to state that cap as a period-wide fact.
 *
 * Payee mode takes the whole response or nothing. It used to take the rows
 * and, optionally, the served totals — and without them it quietly summed
 * the 25 ranked rows and counted 25 payees, the rule the served fields were
 * added to replace. An absent response (still loading) is no payees at all. */
export function buildParetoItems(
  groupBy: GroupBy,
  spendingItems: SpendingGroupItemLike[],
  backendTotal: string | number | undefined,
  payeeReport: PayeeReportLike | undefined
): {
  sorted: ParetoItem[]
  grandTotal: number
  universeCount: number
  /** Served in payee mode, where the client holds only the ranked top 25 and
   *  so cannot find the 80% line itself. Undefined means "compute it". */
  itemsTo80?: number | null
} {
  if (groupBy === 'payee') {
    if (payeeReport === undefined) {
      return { sorted: [], grandTotal: 0, universeCount: 0, itemsTo80: null }
    }
    const items = [...payeeReport.payees].sort((a, b) => Number(b.total) - Number(a.total))
    return {
      sorted: items.map((p) => ({
        id: p.payee_id,
        name: p.payee_name,
        total: Number(p.total),
        groupKey: null,
        groupName: null,
      })),
      // The served total, not a sum of the ranked rows: it covers every
      // payee in the window, and each row's `pct` is a share of it.
      grandTotal: Number(payeeReport.total),
      universeCount: payeeReport.payee_count,
      itemsTo80: payeeReport.payees_to_80pct,
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
      universeCount: items.length,
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
    universeCount: items.length,
  }
}

/** Running share of the grand total for each item, in order (0–100).
 *
 * The line needs a y at every bar, so with no positive total to be a share
 * of it lies on the axis — and never reaches 80%, which is the answer: the
 * card is not drawn (the page also gates it on `grandTotal > 0`). */
export function cumulativePercents(items: ParetoItem[], grandTotal: number): number[] {
  const cumulative = items.reduce<number[]>(
    (acc, item) => [...acc, (acc[acc.length - 1] ?? 0) + item.total],
    []
  )
  return cumulative.map((c) => shareOfTotal(c, grandTotal) ?? 0)
}

/** The 80/20 insight: index of the item whose cumulative share reaches 80%,
 * and what fraction of ALL items that prefix represents.
 *
 * `cumulativePcts` must span every item, not the twenty the chart draws — the
 * chart passed its truncated array, so `findIndex` returned -1 whenever 80%
 * sat past item twenty and the card vanished for exactly the diffuse budgets
 * it exists to warn. `coverage` is unrounded, because a threshold applied to
 * a display-rounded string calls 30.4% adherent. */
export function paretoInsight(
  cumulativePcts: number[],
  totalItemCount: number,
  servedItemsTo80?: number | null
): { idx80: number; coverage: number | null } {
  // Payee mode is served the count: its cumulative line tops out at the top
  // 25's share, so whenever those held under 80% `findIndex` found nothing and
  // the card vanished for diffuse spending. The two sides are held to one
  // answer by `shared/pareto_cases.json`.
  const idx80 =
    servedItemsTo80 === undefined
      ? cumulativePcts.findIndex((pct) => pct >= 80)
      : servedItemsTo80 === null
        ? -1
        : servedItemsTo80 - 1
  const coverage = idx80 >= 0 && totalItemCount > 0 ? ((idx80 + 1) / totalItemCount) * 100 : null
  return { idx80, coverage }
}

/** How many bars the chart draws. The table lists every item. */
export const PARETO_BARS = 20

/** What the page draws: the first `PARETO_BARS` items with their running
 * share, and the 80% insight — measured over EVERY item before the slice.
 *
 * The order is the fix. The chart used to slice first and measure the
 * twenty bars, so a budget whose 80% point sat at item 32 got no card at
 * all. It lived in the component, where no test reached it. */
export function paretoSummary(
  sorted: ParetoItem[],
  grandTotal: number,
  universeCount: number,
  servedItemsTo80?: number | null
): {
  drawn: { item: ParetoItem; cumulativePct: number }[]
  idx80: number
  coverage: number | null
} {
  const cumulativePcts = cumulativePercents(sorted, grandTotal)
  const drawn = sorted
    .slice(0, PARETO_BARS)
    .map((item, i) => ({ item, cumulativePct: cumulativePcts[i] }))
  return { drawn, ...paretoInsight(cumulativePcts, universeCount, servedItemsTo80) }
}

/** Determines if spending adheres to the 80/20 rule.
 * Returns null if data is insufficient, or an object with:
 * - adherent: true if ≤30% of items account for 80% of spending
 * - pct: the actual percentage of items needed for 80%
 * - message: guidance for the user
 *
 * Takes the unrounded coverage. It used to take the string the card renders,
 * so 30.4% of items — which `.toFixed(0)` shows as "30" — was reported as
 * concentrated spending on the wrong side of the line. */
export function paretoAdherence(
  coverage: number | null,
  totalItemCount: number
): { adherent: boolean; pct: number; message: string } | null {
  if (coverage === null || totalItemCount < 3) return null
  const pct = coverage
  if (pct <= 30) {
    return {
      adherent: true,
      pct,
      message: 'Spending is concentrated—easier to optimize the top items.',
    }
  }
  return {
    adherent: false,
    pct,
    message: 'Spending is spread thin—consider consolidating or reviewing smaller items.',
  }
}
