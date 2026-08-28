import type { CategoryGroup } from '../../types'

/**
 * Which category groups the budget page draws.
 *
 * A system (Income) group is where income is filed, not an envelope group:
 * its rows have no assigned or available money (the server serves both as
 * null) and the figure the user wants from it — what is free to assign — is
 * the hero. So the grid and the multi-month sheet leave it out, the way YNAB
 * does. One helper, because the sheet had this filter inline and the grid
 * had none, and a lifetime income total sat in the grid under a hero named
 * Ready to Assign.
 *
 * The server decides which groups *are* system groups (`is_system`); which
 * headers to render is presentation, so this lives on the client.
 */
export function renderableGroups<T extends { is_system: boolean }>(groups: readonly T[]): T[] {
  return groups.filter((g) => !g.is_system)
}

/** The ids of the categories that sit in a renderable group. */
export function renderableCategoryIds(
  groups: readonly CategoryGroup[],
  categories: readonly { id: string; category_group_id: string }[]
): Set<string> {
  const groupIds = new Set(renderableGroups(groups).map((g) => g.id))
  return new Set(categories.filter((c) => groupIds.has(c.category_group_id)).map((c) => c.id))
}
