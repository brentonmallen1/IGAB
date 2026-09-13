/**
 * Clicking anywhere else deselects the budget's selected categories.
 *
 * "Anywhere else" is everything in the page except what acts on the selection:
 * the category and group rows (clicking another row re-selects, and a row's
 * own controls work on it), the inspector, and the floating selection bar.
 * Those spread `keepsSelection`.
 *
 * A click outside the app root keeps the selection too. Every dialog, popover,
 * menu, bottom sheet and toast is portalled to <body>, and those are opened
 * *from* a selected row or the selection bar — the Move to Group menu, a
 * target editor, the delete confirmation — so they must not cancel the thing
 * they are acting on.
 *
 * Pure, with the root passed in, so every branch is a one-line test; the hook
 * beside it does the listening.
 */

export const KEEPS_SELECTION_ATTR = 'data-keeps-selection'

/** Spread on an element that acts on the selection: `<div {...keepsSelection}>`. */
export const keepsSelection = { [KEEPS_SELECTION_ATTR]: '' } as const

export function keepsCategorySelection(
  target: EventTarget | null,
  appRoot: Element | null
): boolean {
  if (!(target instanceof Element)) return true
  if (!appRoot || !appRoot.contains(target)) return true
  return target.closest(`[${KEEPS_SELECTION_ATTR}]`) !== null
}
