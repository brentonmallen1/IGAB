/**
 * When a tooltip shows — the one place, for every Tooltip in the app.
 *
 * Two delays, the pattern people already know from native tooltips and
 * find acceptable: a *cold* delay while the pointer settles on the first
 * thing, then a *warm* window in which moving straight to the next
 * tooltipped thing shows its text at once. Instant from cold flickers as the
 * pointer crosses a row of glyphs; the browser's own second-long cold delay
 * is why the register's hover text felt slow.
 */
export const TOOLTIP_DELAY_MS = 120
export const TOOLTIP_WARM_WINDOW_MS = 500

let lastHiddenAt = -Infinity

/** A tooltip just closed — the next one within the window opens at once. */
export function markTooltipHidden(): void {
  lastHiddenAt = Date.now()
}

export function tooltipDelayNow(): number {
  return Date.now() - lastHiddenAt < TOOLTIP_WARM_WINDOW_MS ? 0 : TOOLTIP_DELAY_MS
}

/** Tests share one module; start each from cold. */
export function resetTooltipWarmth(): void {
  lastHiddenAt = -Infinity
}
