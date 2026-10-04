/**
 * A read-only month's rows, grouped the way YNAB displayed them: groups in
 * first-seen order, categories in YNAB's order within each. Pure, so the
 * grouping is a one-line test rather than a mounted page.
 *
 * Presentation of served rows only — which rows exist, and their figures, are
 * the server's (`ImportHistoryMonthResponse`, already in YNAB's order).
 */
import type { ImportHistoryRow } from '../../../api/budgets'

export interface ImportHistoryGroup {
  name: string
  rows: ImportHistoryRow[]
  /** The group's Available, or null when any row's was unreadable — a sum
   *  that silently skipped one would be a figure YNAB never showed. */
  available: number | null
}

export function groupImportHistory(rows: ImportHistoryRow[]): ImportHistoryGroup[] {
  const groups = new Map<string, ImportHistoryRow[]>()
  for (const row of rows) {
    const list = groups.get(row.category_group)
    if (list) list.push(row)
    else groups.set(row.category_group, [row])
  }
  return [...groups].map(([name, list]) => ({
    name,
    rows: list,
    available: list.some((r) => r.available === null)
      ? null
      : list.reduce((sum, r) => sum + (r.available ?? 0), 0),
  }))
}
