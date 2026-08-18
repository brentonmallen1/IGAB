/**
 * Ref-counted body scroll lock, shared by every overlay primitive.
 *
 * Module-scoped rather than per-component because overlays nest: a picker
 * sheet opened from inside a full-screen editor sheet, or a lightbox opened
 * from inside the transaction editor. Each owner locks on mount and unlocks on
 * unmount; only the first lock and the last unlock touch the DOM, so an inner
 * overlay closing can never release the outer one's lock.
 */

let lockCount = 0

/** Locks body scroll. Every call must be paired with exactly one unlock. */
export function lockBodyScroll() {
  if (++lockCount === 1) document.body.style.overflow = 'hidden'
}

/** Releases one lock. The body only unlocks when the last owner has released. */
export function unlockBodyScroll() {
  if (lockCount === 0) return
  if (--lockCount === 0) document.body.style.overflow = ''
}

/** Test-only: current depth, for asserting balanced lock/unlock pairs. */
export function scrollLockDepth() {
  return lockCount
}
