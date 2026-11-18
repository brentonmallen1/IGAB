/**
 * Clicking anywhere else deselects — the budget's selected categories and the
 * register's selected transactions alike. One rule, one hook
 * (`hooks/useDeselectOnOutsidePointer`), both pages.
 *
 * "Anywhere else" is everything in the page except what acts on the selection.
 * On the budget: the category and group rows (clicking another row re-selects,
 * and a row's own controls work on it) and the inspector. On the register: the
 * transaction rows and their inline editors, the select-all header controls,
 * the split editor, the duplicate-group bar and the reconcile bar. On both: the
 * floating selection bar. Those spread `keepsSelection`.
 *
 * A click outside the app root keeps the selection too. Every dialog, popover,
 * menu, bottom sheet and toast is portalled to <body>, and those are opened
 * *from* a selected row or the selection bar — the Move to Group menu, a
 * target editor, the delete confirmation — so they must not cancel the thing
 * they are acting on.
 *
 * Pure, with the root passed in, so every branch is a one-line test; the hook
 * does the listening.
 */

export const KEEPS_SELECTION_ATTR = 'data-keeps-selection'

/** Spread on an element that acts on the selection: `<div {...keepsSelection}>`. */
export const keepsSelection = { [KEEPS_SELECTION_ATTR]: '' } as const

/** Whether a press on `target` leaves the current selection standing. */
export function pressKeepsSelection(target: EventTarget | null, appRoot: Element | null): boolean {
  if (!(target instanceof Element)) return true
  if (!appRoot || !appRoot.contains(target)) return true
  return target.closest(`[${KEEPS_SELECTION_ATTR}]`) !== null
}
