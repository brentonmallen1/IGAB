/**
 * Grouping categories for a picker. Contains no rule about which are offered.
 *
 * Six components each spelled their own eligibility predicate, and they
 * disagreed three ways:
 *
 *  - The scheduled-transaction editor checked only `is_archived`, so it offered
 *    credit-card payment categories no other surface did.
 *  - Two pickers built a system-group set from the group list, which
 *    `CategoryGroupRepository.get_all` filters by `is_archived` while
 *    `CategoryRepository.get_all` does not — so a hidden system group's
 *    categories leaked into them.
 *  - The liability screen's rule needs `linked_liability_id`, which the API did
 *    not expose, so it could not tell a free category from one another
 *    liability already owned and offered both.
 *
 * The verdicts now arrive on the row as `is_assignable` and `is_categorizable`
 * — the same expressions the assign and cover-overspent endpoints read, so
 * what a picker offers and what the server acts on cannot drift. There is no
 * predicate here: `filingCategoryOptions` reads the served flag, it does not
 * work one out.
 *
 * What *is* shared is the grouping, and one detail in it: a category whose
 * group is missing from `groups` gets a fallback heading rather than being
 * dropped. Dropping it is how categories in a hidden group vanished from a
 * picker while remaining live in the data — the group list is filtered and the
 * category list is not. (A live category under a soft-deleted group is still
 * categorizable, and no group list carries its group.)
 *
 * The flat builder was written six times before it lived here, and the
 * copies disagreed about that heading: the register row, the split editor,
 * bulk categorize and the report filter left it blank, which drew the
 * orphan headerless, run into the list above it. The Guide's planner import
 * called it "Ungrouped". Quick-add and every sectioned picker said
 * `UNGROUPED_LABEL`, which is what all of them say now. Bulk categorize also
 * skipped `is_categorizable`, so it offered every card's envelope.
 */
import type { Category, CategoryGroup } from '../types'

/** Heading for a category whose group is not in the list handed to the picker. */
export const UNGROUPED_LABEL = 'Other'

export interface FlatCategoryOption {
  id: string
  label: string
  group: string
}

/** Flat `{id, label, group}` options, for Combobox and selection-sheet pickers. */
export function flatCategoryOptions(
  categories: Category[],
  groups: CategoryGroup[]
): FlatCategoryOption[] {
  const groupNames = new Map(groups.map((g) => [g.id, g.name]))
  return categories.map((c) => ({
    id: c.id,
    label: c.name,
    group: groupNames.get(c.category_group_id) ?? UNGROUPED_LABEL,
  }))
}

/**
 * What a picker that files a transaction leg offers: the register row, the
 * split editor, quick-add, bulk categorize, and the AI activity row.
 *
 * `is_categorizable` is the server's verdict (`IS_CATEGORIZABLE`, the rule
 * `require_categorizable` enforces on every write), read and never re-derived.
 * One call for all five, because one of the copies, bulk categorize's, forgot it.
 */
export function filingCategoryOptions(
  categories: Category[],
  groups: CategoryGroup[]
): FlatCategoryOption[] {
  return flatCategoryOptions(
    categories.filter((c) => c.is_categorizable),
    groups
  )
}

export interface CategoryGroupSection {
  group: CategoryGroup
  cats: Category[]
}

/** Stand-in group for categories whose real group was not handed to the
 *  picker — usually because the group list is filtered and the category list
 *  is not. Rendering them under a heading beats dropping them silently. */
function ungroupedFallback(budgetId: string): CategoryGroup {
  return {
    id: '__ungrouped__',
    budget_id: budgetId,
    name: UNGROUPED_LABEL,
    sort_order: Number.MAX_SAFE_INTEGER,
    is_archived: false,
    is_system: false,
    system_key: null,
  } as CategoryGroup
}

/**
 * `{group, cats}` sections, for `<optgroup>` renderers. Empty groups are
 * dropped; categories whose group is absent are collected under a final
 * fallback section rather than disappearing.
 */
export function groupedCategorySections(
  categories: Category[],
  groups: CategoryGroup[]
): CategoryGroupSection[] {
  const known = new Set(groups.map((g) => g.id))
  const sections = groups
    .map((group) => ({
      group,
      cats: categories.filter((c) => c.category_group_id === group.id),
    }))
    .filter((s) => s.cats.length > 0)

  const orphans = categories.filter((c) => !known.has(c.category_group_id))
  if (orphans.length > 0) {
    sections.push({ group: ungroupedFallback(orphans[0].budget_id), cats: orphans })
  }
  return sections
}
