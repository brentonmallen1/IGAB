/**
 * How long the pointer rests on something before its tooltip shows — the
 * one value, for every Tooltip in the app.
 *
 * Instant tooltips flicker as the pointer crosses a row of glyphs; the
 * browser's native `title` waits about a second, which is why the register's
 * hover text felt slow. Short enough to read as immediate, long enough that
 * passing over a cell does not open anything.
 */
export const TOOLTIP_DELAY_MS = 180
