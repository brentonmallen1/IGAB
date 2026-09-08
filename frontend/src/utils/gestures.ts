/**
 * Every touch-gesture threshold in the app, in one file.
 *
 * Three copies existed: the budget page's month swipe, the lightbox's
 * prev/next swipe (a duplicate with its own constant) and the bottom sheet's
 * drag-to-dismiss. Pure functions over the numbers a touch handler has, so
 * each rule is a one-line test and the hooks beside them only wire events.
 */

/** Horizontal travel past which a swipe commits. */
export const SWIPE_THRESHOLD_PX = 60
/** A touch that starts this close to the left screen edge is a back gesture,
 *  never a page swipe — the installed PWA has no back gesture of its own. */
export const EDGE_ZONE_PX = 24

export type Swipe = 'left' | 'right' | 'down' | 'edge-back' | null

export interface SwipeInput {
  /** Horizontal travel, end minus start. */
  dx: number
  /** Vertical travel, end minus start. */
  dy: number
  /** Where the touch began, in viewport px from the left. */
  startX: number
  threshold?: number
  edgePx?: number
}

/**
 * What a completed touch was.
 *
 *   - mostly vertical and downward past the threshold → 'down'
 *   - mostly horizontal, rightward, begun inside the edge zone → 'edge-back'
 *   - mostly horizontal past the threshold → 'left' / 'right'
 *   - anything else (a scroll, a tap, a short wobble) → null
 *
 * Axis dominance decides first, so a diagonal scroll never turns a page and
 * a swipe never scrolls it. A start in the edge zone is never a page swipe:
 * one rule, so the month swipe and the back gesture cannot disagree.
 */
export function resolveSwipe({
  dx,
  dy,
  startX,
  threshold = SWIPE_THRESHOLD_PX,
  edgePx = EDGE_ZONE_PX,
}: SwipeInput): Swipe {
  const horizontal = Math.abs(dx) >= Math.abs(dy)
  if (!horizontal) return dy >= threshold ? 'down' : null
  if (Math.abs(dx) < threshold) return null
  if (dx > 0 && startX <= edgePx) return 'edge-back'
  if (startX <= edgePx) return null
  return dx > 0 ? 'right' : 'left'
}

/** Travel past which a slow drag dismisses. */
const DISMISS_DISTANCE_PX = 80
/** ~500 px/s — a deliberate flick rather than a scroll that overshot. */
const DISMISS_VELOCITY_PX_PER_MS = 0.5
/** A flick still has to actually go somewhere. */
const DISMISS_FLICK_DISTANCE_PX = 24

/**
 * Whether a drag should dismiss a sheet.
 *
 * Distance alone made a fast flick that travelled only 60px do nothing, which
 * reads as the sheet being stuck — so a deliberate flick counts even when it
 * falls short of the distance threshold.
 *
 * @param dy   downward travel in px (negative or zero never dismisses)
 * @param dtMs gesture duration in ms
 */
export function shouldDismissDrag(dy: number, dtMs: number): boolean {
  if (dy <= 0) return false
  if (dy > DISMISS_DISTANCE_PX) return true
  return dtMs > 0 && dy / dtMs > DISMISS_VELOCITY_PX_PER_MS && dy > DISMISS_FLICK_DISTANCE_PX
}
