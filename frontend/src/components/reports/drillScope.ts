import type { ReportScope } from '../../api/reports'

/** The scope fields a drill-down carries. */
export interface DrillScope {
  categoryIds?: string[]
  tagIds?: string[]
  filterId?: string | null
}

/**
 * What scope a drill-down should carry, given what the chart is drilling into.
 *
 * The three scope axes UNION on the server, which is right for the filter bar
 * — three controls side by side add up — and wrong for a drill-down, twice
 * over:
 *
 * - A chart drilling into **specific categories** (a treemap tile, a pareto
 *   bar) has already narrowed *within* the scope: its ids are a subset of
 *   what the report counted. Sending the tag as well would union them back out
 *   to the whole tag, so clicking one $80 tile would open a $2,000 list.
 * - A chart drilling into a **day or a month or a payee** has no category ids
 *   of its own. Sending nothing would drop the scope entirely, and the panel
 *   would list every row in the window — the same $2,000 list, from the
 *   opposite mistake.
 *
 * So: its own ids win when it has them; the scope carries when it does not.
 * One statement of that, because it is a rule about every chart and there are
 * eight of them.
 */
export function drillScope(scope: ReportScope, ownCategoryIds?: string[]): DrillScope {
  if (ownCategoryIds !== undefined) return { categoryIds: ownCategoryIds }
  return {
    categoryIds: scope.categoryIds?.length ? scope.categoryIds : undefined,
    tagIds: scope.tagIds?.length ? scope.tagIds : undefined,
    filterId: scope.filterId ?? undefined,
  }
}
