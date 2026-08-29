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

/**
 * A card's set-aside envelope is not a grid row either: the cards section
 * owns it, with liability-truthful columns (Balance / Set aside / Uncovered)
 * instead of assigned/activity/available. `linked_account_id` is the served
 * fact; drawing the row anyway would show the reserve as an ordinary
 * envelope and its negative as overspending, which it is not.
 */
export function renderableCategories<T extends CategoryLink>(categories: readonly T[]): T[] {
  return categories.filter((c) => !isCardEnvelope(c))
}

interface CategoryLink {
  linked_account_id?: string | null
}

/**
 * Is this category a card's set-aside envelope?
 *
 * One predicate rather than an inline comparison at each use, because the
 * two uses need opposite senses and a strict `=== null` gets *both* wrong
 * when the field is absent: the filter drops every category, and the
 * group test reads them all as linked and hides a real group. The server
 * always sends the field, but partial fixtures do not, and a rule that
 * flips meaning on a missing key is a rule waiting to be miswritten.
 */
export function isCardEnvelope(category: CategoryLink): boolean {
  return category.linked_account_id != null
}

/**
 * Groups with a renderable category left in them once the card envelopes are
 * taken out — so "Credit Card Payments" never draws as a bare header, even
 * on the surfaces that deliberately show hidden groups.
 *
 * Returns the input array itself when nothing is dropped. That is
 * load-bearing: BudgetTable's reorder gate asks `visibleGroups === groups`,
 * so a freshly-allocated array with identical contents would silently turn
 * dragging off.
 *
 * A group with no categories at all is kept — an empty group the user just
 * made still needs its header to drop things into.
 */
export function withoutCardOnlyGroups<G extends { id: string }>(
  groups: G[] | undefined,
  categories: readonly ({ category_group_id: string } & CategoryLink)[]
): G[] | undefined {
  if (!groups) return groups
  const cardOnly = new Set(
    groups
      .filter((g) => {
        const inGroup = categories.filter((c) => c.category_group_id === g.id)
        return inGroup.length > 0 && inGroup.every(isCardEnvelope)
      })
      .map((g) => g.id)
  )
  return cardOnly.size > 0 ? groups.filter((g) => !cardOnly.has(g.id)) : groups
}

/** The ids of the categories that sit in a renderable group. */
export function renderableCategoryIds(
  groups: readonly CategoryGroup[],
  categories: readonly ({ id: string; category_group_id: string } & CategoryLink)[]
): Set<string> {
  const groupIds = new Set(renderableGroups(groups).map((g) => g.id))
  return new Set(
    renderableCategories(categories)
      .filter((c) => groupIds.has(c.category_group_id))
      .map((c) => c.id)
  )
}
