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
