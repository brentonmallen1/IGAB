/**
 * Ordering for every dismissable overlay in the app — sheets, modals, drawers.
 *
 * Escape and the Android back gesture must reach exactly one overlay: the
 * topmost. That requires a single stack shared across primitives. Before this
 * existed, BottomSheet kept a private stack and the hand-rolled modals kept
 * none, so a modal opened from inside a sheet had no ordering relationship at
 * all and both would close on one Escape.
 *
 * Registration order is mount order, which matches paint order: every overlay
 * portals to document.body, so the most recently opened is last in the DOM and
 * renders on top.
 */

const stack: symbol[] = []

/** Registers an overlay as the new topmost. */
export function pushOverlay(id: symbol) {
  if (!stack.includes(id)) stack.push(id)
}

/** Removes an overlay from anywhere in the stack — closing need not be LIFO. */
export function popOverlay(id: symbol) {
  const i = stack.indexOf(id)
  if (i !== -1) stack.splice(i, 1)
}

/** True when `id` is the overlay a dismiss gesture should reach. */
export function isTopOverlay(id: symbol) {
  return stack.length > 0 && stack[stack.length - 1] === id
}

/** Test-only: current depth. */
export function overlayStackDepth() {
  return stack.length
}
