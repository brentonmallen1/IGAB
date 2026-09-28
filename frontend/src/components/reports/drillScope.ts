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
 * - A chart drilling into **specific categories** (a treemap tile, a ranked
 *   row) has already narrowed *within* the scope: its ids are a subset of
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

/** The client key of a category line: its id, or this for the Uncategorized
 *  line, which has none (served with `id: null`). A key no id can be, so a
 *  category someone named "Uncategorized" is not the line. */
export const UNCATEGORIZED_KEY = '__uncategorized__'

export function categoryKey(id: string | null): string {
  return id ?? UNCATEGORIZED_KEY
}

/**
 * Which rows a category line — or a group of them — opens.
 *
 * The Uncategorized line has no id, so it opens by `noCategory`; an empty
 * `categoryIds` would filter nothing and list the whole window. A group is
 * either categories or the Uncategorized line alone (the server files
 * uncategorized spending under a group of its own), so the two are never
 * sent together — they would AND, and match nothing.
 */
export function categoryTarget(
  ids: readonly (string | null)[]
): Pick<DrillScope, 'categoryIds'> & { noCategory?: true } {
  const real = ids.filter((id): id is string => id !== null)
  return real.length === 0 ? { noCategory: true } : { categoryIds: real }
}
