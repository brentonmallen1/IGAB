/**
 * Whether a scroll container should follow new content.
 *
 * A chat that scrolls on every token fights the person who scrolled up to
 * re-read a figure — the answer keeps yanking them back to the bottom while
 * they are still reading the middle. So it follows only when they were already
 * at the bottom, which is the same rule every readable chat uses.
 *
 * Pure, so the threshold is a one-line test rather than something you have to
 * reproduce by scrolling in a browser.
 */

/**
 * How far from the bottom still counts as "at the bottom", in px.
 *
 * Not zero: sub-pixel line heights and a mid-stream reflow leave a container
 * a pixel or two short, and a zero threshold would read that as "the user
 * scrolled away" and stop following on its own.
 */
export const STICK_THRESHOLD_PX = 48

export interface ScrollPosition {
  scrollTop: number
  scrollHeight: number
  clientHeight: number
}

export function isAtBottom(
  { scrollTop, scrollHeight, clientHeight }: ScrollPosition,
  threshold: number = STICK_THRESHOLD_PX
): boolean {
  // A container shorter than its viewport cannot be scrolled away from.
  if (scrollHeight <= clientHeight) return true
  return scrollHeight - (scrollTop + clientHeight) <= threshold
}
