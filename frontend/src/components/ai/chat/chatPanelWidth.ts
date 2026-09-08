/** The chat panel's resizable width, in px.
 *
 *  360 is wide enough for a paragraph and a tool disclosure without wrapping
 *  every figure; below that the panel stops being readable and the toggle is
 *  the right tool instead. The ceiling exists because the panel sits beside
 *  the page rather than over it — past ~560 it starts squeezing the register
 *  it is meant to help you read. */
export const CHAT_PANEL_MIN_WIDTH = 360
export const CHAT_PANEL_MAX_WIDTH = 560
/** Arrow-key increment on the resize handle. */
export const CHAT_PANEL_KEY_STEP = 16

export function clampChatPanelWidth(px: number): number {
  if (!Number.isFinite(px)) return CHAT_PANEL_MIN_WIDTH
  return Math.round(Math.min(CHAT_PANEL_MAX_WIDTH, Math.max(CHAT_PANEL_MIN_WIDTH, px)))
}
