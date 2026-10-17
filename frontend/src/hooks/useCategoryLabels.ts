import { useMemo } from 'react'
import { useCategories, useCategoryGroups } from '../api/categories'
import type { Category, CategoryGroup } from '../types'
import { buildCategoryLabels, type NamedCategory } from '../utils/categoryLabels'

const NO_CATEGORIES: Category[] = []
const NO_GROUPS: CategoryGroup[] = []

/**
 * id → `{name, group}` for every category a row could be filed in — the
 * wiring for `buildCategoryLabels`.
 *
 * Archived included, categories and groups both: this names rows, it never
 * offers a choice, and a row filed in an envelope archived since still needs
 * a name. Pickers keep reading their own lists through `filingCategoryOptions`.
 * A null budget (a closed palette, say) loads nothing and names nothing.
 */
export function useCategoryLabels(budgetId: string | null): ReadonlyMap<string, NamedCategory> {
  const { data: categories = NO_CATEGORIES } = useCategories(budgetId, true)
  const { data: groups = NO_GROUPS } = useCategoryGroups(budgetId, true)
  return useMemo(() => buildCategoryLabels(categories, groups), [categories, groups])
}
