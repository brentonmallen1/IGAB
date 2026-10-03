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
 * The Credit cards section's envelopes are not grid rows: each card's own
 * envelope, drawn there with liability-truthful columns (Balance / Set aside /
 * Uncovered), and the budget's Interest & fees envelope, drawn there as an
 * ordinary row under the cards that charge it.
 *
 * Reads the served `in_card_section` and does not re-derive it — home is
 * `CARD_SECTION_CATEGORY` in repositories/category_filters.py, which the
 * server's `is_card_only` and category reorder read too, so the grid, the
 * group headers and a drag cannot disagree about a row. This read
 * `linked_account_id` until Interest & fees existed: an envelope that is in
 * the section without being linked to anything.
 */
export function renderableCategories<T extends CategoryPlacement>(categories: readonly T[]): T[] {
  return categories.filter((c) => !inCardSection(c))
}

interface CategoryPlacement {
  in_card_section?: boolean
}

interface CategoryLink {
  linked_account_id?: string | null
}

/**
 * Is this category drawn in the Credit cards section?
 *
 * Absent reads as "no", so a partial fixture keeps its rows in the grid
 * rather than silently dropping every one of them. The server always sends
 * the field (`CategoryResponse` requires it).
 */
export function inCardSection(category: CategoryPlacement): boolean {
  return category.in_card_section === true
}

/**
 * Is this category a card's OWN envelope — the reserve card arithmetic keeps,
 * which nothing is ever filed to?
 *
 * A different question from `inCardSection`, and the difference matters to
 * exactly one kind of surface: one that asks where money was SPENT. Interest &
 * fees is in the section and is spent from like any envelope, so a report
 * filter must offer it; a card's envelope can only ever return an empty chart.
 * `linked_account_id` is the served fact. `!= null` rather than `!== null` so a
 * fixture without the field reads as "not a card's envelope".
 */
export function isCardEnvelope(category: CategoryLink): boolean {
  return category.linked_account_id != null
}

/**
 * The Credit cards section's one ordinary envelope — Interest & fees — or
 * null when the budget has none on screen (archived, or no card yet).
 *
 * In the section and not a card's own envelope: the server keys exactly one
 * such envelope per budget, so this names it without the client knowing the
 * key or the name, both of which are the server's.
 */
export function cardSectionEnvelope<T extends CategoryPlacement & CategoryLink>(
  categories: readonly T[]
): T | null {
  return categories.find((c) => inCardSection(c) && !isCardEnvelope(c)) ?? null
}

/**
 * The section envelope the budget page actually DRAWS: `cardSectionEnvelope`,
 * but only while the Credit cards section is drawn at all — which is while the
 * month has a card. The section and the filter bar's counts both ask this, so
 * a chip cannot count a row the section is not there to show.
 */
export function drawnCardSectionEnvelope<T extends CategoryPlacement & CategoryLink>(
  categories: readonly T[],
  cardCount: number
): T | null {
  return cardCount > 0 ? cardSectionEnvelope(categories) : null
}

/**
 * Every envelope row the budget page draws — the grid's rows, narrowed by an
 * active view, plus the Credit cards section's rows: each card line (by its
 * envelope) and the section's own envelope (Interest & fees).
 *
 * What the filter bar's chips count ("Overspent 3", "Underfunded 2"). A chip's
 * count and the rows clicking it shows must be one set. Interest & fees is a
 * row like any other: red, it is in the served `total_overspent` and in Cover
 * Overspent, so a chip that left it out would say 2 over three red rows. Card
 * lines joined when filters began to reach them: a card's envelope below zero
 * is overspent the same way, and once the chip draws its line it has to count
 * it. A view does not reach the section — a view arranges the grid, and the
 * section is not the grid — so its rows are counted whatever view is active.
 */
export function budgetPageRowIds({
  gridIds,
  viewIds,
  sectionIds,
}: {
  gridIds: ReadonlySet<string>
  viewIds: ReadonlySet<string> | null
  sectionIds: readonly string[]
}): Set<string> {
  const ids = new Set([...gridIds].filter((id) => !viewIds || viewIds.has(id)))
  for (const id of sectionIds) ids.add(id)
  return ids
}

/**
 * Groups the grid draws — everything but the ones holding nothing except card
 * card envelopes, so "Credit Card Payments" never appears as a bare
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
  categories: readonly ({ id: string; category_group_id: string } & CategoryPlacement)[]
): Set<string> {
  const groupIds = new Set(renderableGroups(groups).map((g) => g.id))
  return new Set(
    renderableCategories(categories)
      .filter((c) => groupIds.has(c.category_group_id))
      .map((c) => c.id)
  )
}
