/**
 * Naming a category: its own name, its group's, and what a row shows for it.
 *
 * Two envelopes may share a name in different groups — "Gifts" under
 * Holidays and under Birthdays — so a name alone cannot say which one a row
 * is filed in. Every list that draws a row's category names it from here,
 * with the group a hover away (`categoryPath`).
 *
 * This is *naming*, not *choosing*: the lists handed in should include
 * archived categories and archived groups (`useCategoryLabels` loads them
 * that way). A row filed in an envelope archived since still exists, and the
 * register drew "—" for it when it named from the picker's list — the same
 * mistake `accountLists.ts` describes for closed accounts.
 *
 * Before this lived here, seven transaction lists built their own
 * id → name map and they disagreed about a category they could not name:
 * the register, its split lines and the merge preview drew "—", the report
 * drill-down drew nothing, and the SimpleFIN match review's merged preview
 * dropped its Category line outright. Two more surfaces that showed a group
 * beside the name (the import review, the AI activity row) each built a
 * group map of their own.
 */
import type { Category, CategoryGroup } from '../types'

/** Heading for a category whose group is not in the list handed in — the
 *  picker's section title for it, and the group half of its path. */
export const UNGROUPED_LABEL = 'Other'

/** What a row shows for a category id it cannot name (deleted, or the list
 *  has not arrived). */
export const UNKNOWN_CATEGORY = '—'

/** A category as a label can name it: its own name and its group's. */
export interface NamedCategory {
  name: string
  /** Null when the group is not in the list the caller holds. Never a
   *  stand-in: the AI label matcher reads this, and "Gifts (Other)" must not
   *  match a category whose group simply was not loaded. Display goes
   *  through `groupHeading`, which supplies the stand-in. */
  group: string | null
}

type NameableCategory = Pick<Category, 'id' | 'name' | 'category_group_id'>
type NameableGroup = Pick<CategoryGroup, 'id' | 'name'>

/** id → `{name, group}` for every category handed in. */
export function buildCategoryLabels(
  categories: readonly NameableCategory[],
  groups: readonly NameableGroup[]
): Map<string, NamedCategory> {
  const groupNames = new Map(groups.map((g) => [g.id, g.name]))
  return new Map(
    categories.map((c) => [
      c.id,
      { name: c.name, group: groupNames.get(c.category_group_id) ?? null },
    ])
  )
}

/** The group as a heading reads it: its name, or `UNGROUPED_LABEL`. */
export function groupHeading(label: NamedCategory): string {
  return label.group ?? UNGROUPED_LABEL
}

/** "Group › Category" — the hover on a row's category. */
export function categoryPath(label: NamedCategory): string {
  return `${groupHeading(label)} › ${label.name}`
}

/** What a cell draws for a category id: the name, and the path for its
 *  hover. An id the labels cannot name reads `UNKNOWN_CATEGORY` with no
 *  hover — there is no group to show. */
export interface CategoryDisplay {
  name: string
  path: string | null
}

export function categoryDisplay(
  id: string,
  labels: ReadonlyMap<string, NamedCategory>
): CategoryDisplay {
  const label = labels.get(id)
  return label
    ? { name: label.name, path: categoryPath(label) }
    : { name: UNKNOWN_CATEGORY, path: null }
}

/** id → name, for the search parser and its chips, which resolve a typed
 *  name the way they resolve payees and accounts. Derived from the labels so
 *  the parser cannot name a different set of categories than the rows do. */
export function categoryNames(labels: ReadonlyMap<string, NamedCategory>): Map<string, string> {
  return new Map([...labels].map(([id, label]) => [id, label.name]))
}
