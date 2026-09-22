import type { Transaction } from '../../../types'

/**
 * Arriving at a transaction must show that transaction.
 *
 * Every "show me this row" path in the app — the budget page's peek modal,
 * the command palette, the AI activity list — navigates to
 * `?highlight=<id>` and trusts the register to put that row on screen. Two
 * pieces of register state could silently refuse:
 *
 * 1. **A search that is still running.** `transactionSearchQuery` is
 *    register-scoped state living in a global store, and it feeds the SERVER
 *    query — so a leftover search does not merely hide the row, the row is
 *    never fetched. The register then draws "No transactions match your
 *    search" over the thing you just asked to see.
 * 2. **A collapsed section.** `Collapsible` renders no children while shut,
 *    so a pending or needs-review row inside one is absent from the DOM
 *    entirely — the highlight effect's `querySelector` fallback finds
 *    nothing, and neither does the reader. Pending starts collapsed by
 *    default and the fold is persisted, so this is the common case rather
 *    than the odd one.
 *
 * The two are fixed differently on purpose. The search is *cleared*: it is
 * leftover state, and a register showing an unrelated filter is wrong
 * whatever brought you there. The fold is *overridden for as long as the
 * highlight lasts* and never written — a fold is a standing choice the
 * person made, and spending it to show one row would mean they have to
 * refold the section afterwards. Derived, not stored, the same way
 * `resolveHeaderCollapsed` derives the account header's fold rather than
 * writing one.
 */

/** Does this section hold the highlighted row? */
export function holdsHighlight(
  rows: readonly Pick<Transaction, 'id'>[],
  highlightId: string | null | undefined
): boolean {
  return highlightId != null && rows.some((r) => r.id === highlightId)
}

/**
 * Whether a register section renders open, from the stored fold and whether
 * it is hiding the row somebody navigated here to see.
 *
 * One spelling for all three sections. Written inline at each `Collapsible`
 * it would be three copies of one rule, and the third is exactly the one
 * that gets forgotten.
 */
export function sectionOpen(
  collapsed: ReadonlySet<string>,
  section: string,
  rows: readonly Pick<Transaction, 'id'>[],
  highlightId: string | null | undefined
): boolean {
  return holdsHighlight(rows, highlightId) || !collapsed.has(section)
}

/**
 * Should the register drop the search it is carrying?
 *
 * Only when there is one AND a row has been asked for by id. Returning false
 * on an empty query matters: the effect that calls this must not write to the
 * store on every render, and "clear a search that is already clear" is a
 * write that re-renders every consumer of the store.
 */
export function shouldDropSearch(query: string, highlightId: string | null | undefined): boolean {
  return highlightId != null && query.trim() !== ''
}

/**
 * How many pages the register will pull looking for a row it was sent to.
 *
 * At a hundred rows a page that is ten thousand transactions — far past any
 * register somebody scrolls, and the loop stops the moment the row arrives,
 * so the cost is only paid when the row genuinely is not here. The cap is
 * what keeps a stale link (a deleted transaction, an id from another budget)
 * from walking an entire account one request at a time.
 */
export const HIGHLIGHT_PAGE_BUDGET = 100

/**
 * Should the register fetch another page to find the row it was sent to?
 *
 * The third way "show me this transaction" silently failed, and the one that
 * only appears on a real account: the register pages newest-first, so a row
 * from four months ago is not in the first page and the scroll effect looks
 * for an index that does not exist yet. Nothing errors. The reader gets the
 * top of the register and no explanation.
 *
 * An options object rather than five positional booleans, because four of
 * these are booleans and their order is exactly the kind of thing that is
 * wrong for a year.
 */
export function shouldPageForHighlight({
  highlightId,
  isLoaded,
  pagesLoaded,
  hasNextPage,
  isFetching,
}: {
  highlightId: string | null | undefined
  /** Is the row already among the pages in hand? */
  isLoaded: boolean
  hasNextPage: boolean
  isFetching: boolean
  pagesLoaded: number
}): boolean {
  if (highlightId == null || isLoaded) return false
  if (!hasNextPage || isFetching) return false
  return pagesLoaded < HIGHLIGHT_PAGE_BUDGET
}
