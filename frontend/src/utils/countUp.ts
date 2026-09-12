import { fromCents, toCents } from './money'

/** How long a figure takes to count from its old value to its new one. */
export const COUNT_UP_MS = 600

/** Ease-out cubic: quick off the mark, settling onto the final figure. */
function easeOut(t: number): number {
  return 1 - (1 - t) ** 3
}

/**
 * The figure to print `elapsedMs` into a count from `from` to `to`.
 *
 * Presentation only — both ends are served figures and nothing here decides
 * a balance. Every frame is a whole number of cents, so a counting figure
 * never prints a fraction of a cent the formatter would round differently
 * from frame to frame. The last frame returns `to` itself rather than a
 * rebuilt copy, so where the count stops is exactly what the server said.
 */
export function countUpValue(
  from: number,
  to: number,
  elapsedMs: number,
  durationMs = COUNT_UP_MS
): number {
  if (durationMs <= 0 || elapsedMs >= durationMs) return to
  if (elapsedMs <= 0) return from
  const start = toCents(from)
  const end = toCents(to)
  return fromCents(Math.round(start + (end - start) * easeOut(elapsedMs / durationMs)))
}
