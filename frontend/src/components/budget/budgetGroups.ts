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
 * Groups the grid draws — everything but the ones holding nothing except card
 * set-aside envelopes, so "Credit Card Payments" never appears as a bare
 * header, even on the surfaces that deliberately show hidden groups.
 *
 * Reads the served `is_card_only`; it does NOT re-derive it. The client cannot:
 * its category list filters hidden categories, so a group whose only non-card
 * row is hidden would read as card-only here and not on the server. It derived
 * it anyway, and the server's reorder rule had a second, narrower idea of the
 * same thing — so dragging a group was refused on any budget with a card group,
 * and the identity-preservation trick this function used to need turned the
 * drag handles off before a request was even attempted. Home is
 * `GROUP_IS_CARD_ONLY` in repositories/category_filters.py.
 *
 * A group with no categories at all is kept — an empty group the user just
 * made still needs its header to drop things into. The server agrees: an empty
 * group is not card-only.
 */
export function drawnGroups<G extends { is_card_only: boolean }>(
  groups: G[] | undefined
): G[] | undefined {
  return groups?.filter((g) => !g.is_card_only)
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
