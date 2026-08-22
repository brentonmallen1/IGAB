import type { BudgetView, Category, CategoryGroup } from '../../../types'

/** Categories with no placement, or placed in no group, collect here. Rendered
 *  last. The bucket exists so that a category added after a view was built
 *  cannot silently vanish from it. */
export const UNASSIGNED_GROUP_ID = '__unassigned__'

export interface ViewGrouping {
  /** Groups to render, in order. Standing in for CategoryGroup so the existing
   *  row component can render them — they are not real groups, so the caller
   *  renders them read-only. */
  groups: CategoryGroup[]
  /** group id → the categories in it, in the view's order. */
  byGroup: Map<string, Category[]>
}

/**
 * Arrange categories according to a view rather than the budget's own groups.
 *
 * `categories` should already have any filter and search applied — a view
 * decides the arrangement, a filter decides which categories show, and the two
 * are independent.
 */
export function groupByView(
  view: BudgetView,
  categories: Category[],
  budgetId: string
): ViewGrouping {
  const placementBy = new Map(view.placements.map((p) => [p.category_id, p]))
  const byGroup = new Map<string, Category[]>()

  for (const cat of categories) {
    const placement = placementBy.get(cat.id)
    // Hidden in this view: out of the grid and out of its group totals.
    if (placement?.is_hidden) continue
    const bucket = placement?.group_id ?? UNASSIGNED_GROUP_ID
    if (!byGroup.has(bucket)) byGroup.set(bucket, [])
    byGroup.get(bucket)!.push(cat)
  }

  for (const list of byGroup.values()) {
    list.sort(
      (a, b) =>
        (placementBy.get(a.id)?.sort_order ?? 0) - (placementBy.get(b.id)?.sort_order ?? 0)
    )
  }

  const asGroup = (id: string, name: string, sort_order: number): CategoryGroup => ({
    id,
    budget_id: budgetId,
    name,
    sort_order,
    is_hidden: false,
    is_system: false,
  })

  const groups = [...view.groups]
    .sort((a, b) => a.sort_order - b.sort_order)
    .map((g) => asGroup(g.id, g.name, g.sort_order))

  if (byGroup.has(UNASSIGNED_GROUP_ID)) {
    groups.push(asGroup(UNASSIGNED_GROUP_ID, 'Unassigned', Number.MAX_SAFE_INTEGER))
  }

  return { groups, byGroup }
}
