/**
 * How the Discretionary report lays out what the server sent, and nothing more.
 *
 * The server decides which rows are discretionary — that is a rule about rows,
 * `domain.activity_class.DISCRETIONARY_ROW` — and serves the totals. What the
 * page makes of them is pure composition of served figures with no missing
 * input, so by the boundary rule it lives here, once: the share of spending,
 * each line's share, the table's rows, and what a click on any of them opens.
 */
import type { DrillDownContext } from '../../../stores/reportStore'
import type { DiscretionaryGroup, DiscretionaryReport } from '../../../types'
import { monthWindow } from '../../../utils/dateWindow'
import { shareOfTotal } from '../drillDownTotals'

/**
 * Discretionary as a percentage of all spending over the same window, 0–100.
 *
 * Null when either figure is — nothing tagged, so no figure was served — and
 * when there is no positive spending to be a share of (`shareOfTotal`). The
 * two are the same rows by construction (the discretionary rows are a cut of
 * the SPENDING class), so this is a true part-of-whole, not two reports
 * divided by each other.
 */
export function discretionaryShare(
  report: Pick<DiscretionaryReport, 'total' | 'spending_total'>
): number | null {
  if (report.total === null || report.spending_total === null) return null
  return shareOfTotal(report.total, report.spending_total)
}

/** Which rows a table line opens, before the window is attached. */
export type DiscretionaryTarget = { categoryIds: string[] } | { noCategory: true }

export interface DiscretionaryRow {
  key: string
  /** A group heading its categories, one of those categories, or the
   *  Uncategorized line, which has no categories to head. */
  kind: 'group' | 'category' | 'uncategorized'
  label: string
  avgMonthly: number
  total: number
  /** Share of the discretionary total, 0–100 — so the group rows add to 100
   *  and the category rows add to their group's. Null with no positive total. */
  share: number | null
  target: DiscretionaryTarget
}

/**
 * The table, in order: each group, then its categories, biggest first as
 * served. The Uncategorized line is one row and opens by "no category".
 *
 * A group opens every category under it. Its ids are the categories the
 * server listed — the ones with discretionary rows in the window — which is
 * exactly the set its total was summed from.
 */
export function discretionaryRows(groups: DiscretionaryGroup[], total: number): DiscretionaryRow[] {
  const rows: DiscretionaryRow[] = []
  for (const g of groups) {
    const share = shareOfTotal(g.total, total)
    if (g.group_id === null) {
      rows.push({
        key: 'uncategorized',
        kind: 'uncategorized',
        label: g.group_name,
        avgMonthly: g.avg_monthly,
        total: g.total,
        share,
        target: { noCategory: true },
      })
      continue
    }
    rows.push({
      key: `group-${g.group_id}`,
      kind: 'group',
      label: g.group_name,
      avgMonthly: g.avg_monthly,
      total: g.total,
      share,
      target: { categoryIds: g.categories.map((c) => c.category_id) },
    })
    for (const c of g.categories) {
      rows.push({
        key: `category-${c.category_id}`,
        kind: 'category',
        label: c.category_name,
        avgMonthly: c.avg_monthly,
        total: c.total,
        share: shareOfTotal(c.total, total),
        target: { categoryIds: [c.category_id] },
      })
    }
  }
  return rows
}

/** The report's window, as a drill carries it. */
export interface DrillWindow {
  startDate: string
  endDate: string
}

/**
 * The drill behind a table line. Always the report's own predicate
 * (`discretionary`): a line's categories alone would also list rows filed to
 * them that are not discretionary spending — a move to savings, a purchase on
 * an off-budget account — and the panel would total more than the line.
 */
export function discretionaryDrill(row: DiscretionaryRow, window: DrillWindow): DrillDownContext {
  return {
    kind: row.kind === 'category' ? 'category' : 'category-group',
    label: row.label,
    // Categories live on split children, so the drill counts leaves — the
    // scope the report's own query uses.
    scope: 'leaf',
    discretionary: true,
    ...('noCategory' in row.target
      ? { noCategory: true }
      : { categoryIds: row.target.categoryIds }),
    ...window,
  }
}

/** The drill behind one month's bar: every discretionary row in that month.
 *  Every month the report serves is complete, so its window is the whole
 *  calendar month. */
export function discretionaryMonthDrill(month: string, label: string): DrillDownContext {
  const { start, end } = monthWindow(month)
  return {
    kind: 'month',
    label,
    scope: 'leaf',
    discretionary: true,
    startDate: start,
    endDate: end,
  }
}
