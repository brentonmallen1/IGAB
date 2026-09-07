/**
 * How many saved filters the budget bar draws as chips, and which.
 *
 * The bar rendered one button per saved filter, unbounded. It wraps, and the
 * grid offsets its sticky column header by this bar's *measured height* — so
 * every filter someone saved pushed the register further down the page. Five
 * is fine and twenty is a wall, which is a thing that gets worse the more
 * someone uses the feature.
 *
 * The view control had already solved this: one chip that opens a picker. The
 * difference here is that a filter is a thing you reach for by name several
 * times a day, so collapsing all of them behind a menu would trade one problem
 * for a slower one. Hence: a few pinned, the rest behind the picker.
 *
 * **Pinning is `sort_order`, not a new column.** The order is already the
 * user's — Manage Filters reorders it — so "the ones I put first" is a
 * statement they have already made, and a `pinned` boolean would be a second
 * way to say it that could disagree with the first.
 *
 * **The active filter always gets a chip**, pinned or not. The bar's job is to
 * say what is narrowing the grid; hiding that inside a picker would leave a
 * short category list with no visible reason for it.
 */

export interface ChipFilter {
  id: string
  name: string
}

export interface FilterChips<T> {
  /** Drawn as buttons, in order. */
  chips: T[]
  /** Behind the picker. May be empty, in which case draw no picker. */
  overflow: T[]
}

/** How many stay on the bar before the picker takes over. Three fits beside
 *  the quick filters at a laptop width without wrapping, and is enough for the
 *  handful anyone reaches for daily. */
export const PINNED_FILTER_COUNT = 3

export function filterChips<T extends ChipFilter>(
  filters: readonly T[],
  activeId: string | null,
  pinned: number = PINNED_FILTER_COUNT
): FilterChips<T> {
  const chips = filters.slice(0, pinned)
  const rest = filters.slice(pinned)

  const activeInRest = activeId != null ? rest.find((f) => f.id === activeId) : undefined
  if (!activeInRest) return { chips, overflow: rest }

  // Appended rather than swapped into the pinned run: the pinned three keep
  // their places, so choosing a filter from the picker does not reshuffle the
  // chips the user navigates by.
  return {
    chips: [...chips, activeInRest],
    overflow: rest.filter((f) => f.id !== activeId),
  }
}
