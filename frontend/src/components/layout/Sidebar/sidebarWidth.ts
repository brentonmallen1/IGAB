/** The sidebar's resizable width, in px. 240 is the shipped width and the
 *  narrowest it goes before the collapse control is the right tool. */
export const SIDEBAR_MIN_WIDTH = 240
export const SIDEBAR_MAX_WIDTH = 440
/** Arrow-key increment on the resize handle. */
export const SIDEBAR_KEY_STEP = 16

export function clampSidebarWidth(px: number): number {
  if (!Number.isFinite(px)) return SIDEBAR_MIN_WIDTH
  return Math.round(Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, px)))
}
