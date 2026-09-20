/**
 * Cell editors — the one-keystroke amount boxes in the budget grid, the
 * credit-card strip and the multi-month sheet.
 *
 * They are `<input>`s, so the global-shortcut guard (`isEditableTarget`)
 * treated them like a memo field and swallowed ⌘Z. That is wrong for a cell:
 * committing one with Enter opens the NEXT row's box, so after assigning
 * money the focus is always inside one of these, and ⌘Z went to the
 * browser's text-undo for a box the user had not typed in — the report was
 * "undo doesn't work for assigning money to a category". The change row was
 * always recorded; the keystroke never reached it.
 *
 * Marking a box with `data-cell-editor` says: this is a cell, not a
 * document. Undo/redo pass through it, and `cancelCellEdit` shuts it first
 * so the box does not sit open over a figure the undo just moved — and
 * cannot commit its now-stale draft on the way out.
 */

/** Spread onto a cell editor's input. */
export const CELL_EDITOR_PROPS = { 'data-cell-editor': '' } as const

export function isCellEditor(el: Element | null): el is HTMLElement {
  return el instanceof HTMLElement && el.hasAttribute('data-cell-editor')
}

/**
 * Close the focused cell editor without committing, as Escape does — every
 * one of these boxes already treats Escape as "cancel", so this asks them in
 * their own vocabulary rather than adding a second way to close.
 *
 * Escape and nothing else — deliberately no `blur()` chaser. Blur is how
 * these boxes COMMIT, so a blur racing the Escape re-render writes back the
 * very draft this is trying to drop; a test pins that. Escape unmounts the
 * input, which takes the focus with it.
 *
 * Returns whether there was one to close.
 */
export function cancelCellEdit(): boolean {
  const el = document.activeElement
  if (!isCellEditor(el)) return false
  el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
  return true
}
