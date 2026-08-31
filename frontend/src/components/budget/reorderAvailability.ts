/**
 * When the budget grid may be rearranged, and what to say when it may not.
 *
 * Reordering is suppressed for two reasons, both legitimate:
 *
 * - **Filtered.** A searched or filtered grid hides rows, so a drop would
 *   rearrange a list the user cannot fully see — and the server refuses a
 *   reorder that omits a group the grid draws, so it would fail anyway.
 * - **A view is active.** A view carries its own arrangement, edited in the
 *   view editor; the budget's own order is not what is on screen.
 *
 * One home, because the answer is read twice: the grid turns the drag handles
 * off with it, and the filter bar explains itself with it. Derived separately
 * they would drift, and the failure mode is silent — a handle that is simply
 * absent, with a line elsewhere claiming a different reason, or none.
 *
 * That silence is the point. The handle is deliberately always visible at rest
 * rather than on hover (DragHandle.css: hover-only is unreachable by keyboard),
 * so when it goes the user sees something disappear and has nothing to connect
 * it to. Group reordering had exactly this failure for a third reason, now
 * fixed: a hidden card-only group reaching the client with "show hidden" on
 * broke an identity check in the gate, so one person could reorder and another
 * could not, on the same build and the same budget.
 *
 * Pure: takes the state, returns the answer. No store, no query, no DOM.
 */

export interface ReorderState {
  /** A saved filter is selected. */
  savedFilterActive: boolean
  /** One of the quick-filter chips is on. */
  quickFilterActive: boolean
  /** The category search box's raw value. */
  search: string
  /** A saved view is active. */
  viewActive: boolean
}

export interface ReorderBlock {
  reason: 'view' | 'filtered'
  /** One line, for the filter bar. States the fact, not a warning. */
  short: string
  /** Why, and the way out — the accessible name and the tooltip. */
  detail: string
}

const VIEW: ReorderBlock = {
  reason: 'view',
  short: 'This view keeps its own order',
  detail:
    'Groups and categories follow this view’s own arrangement, which is edited in the view editor. Switch to Default groups to rearrange the budget itself.',
}

const FILTERED: ReorderBlock = {
  reason: 'filtered',
  short: 'Ordering is off while filtered',
  detail:
    'A filtered grid hides rows, so a drop here would rearrange a list you cannot fully see. Clear the search and filters to drag again.',
}

/**
 * Why reordering is unavailable, or null when it is available.
 *
 * A view outranks a filter: clearing the filter would not restore dragging
 * while the view still owns the order, so naming the filter would send the
 * user to do something that changes nothing.
 */
export function reorderBlock(state: ReorderState): ReorderBlock | null {
  if (state.viewActive) return VIEW
  if (state.savedFilterActive || state.quickFilterActive || state.search.trim() !== '') {
    return FILTERED
  }
  return null
}

/** Categories may be rearranged within their group. */
export function canReorderCategories(state: ReorderState): boolean {
  return reorderBlock(state) === null
}

/**
 * Groups may be rearranged.
 *
 * The extra condition is that there is more than one group to put in an order.
 * It is deliberately NOT a reason: a single-group budget needs no explanation
 * for the absence of an ordering it could not have.
 */
export function canReorderGroups(state: ReorderState, drawnGroupCount: number): boolean {
  return canReorderCategories(state) && drawnGroupCount > 1
}
