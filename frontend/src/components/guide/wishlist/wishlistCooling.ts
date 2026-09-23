/**
 * A wish's cooling-off, as the form reads and writes it: a number of days
 * after the wish was added, or the date that lands on.
 *
 * The server decides the stored date (`cooling_until_for` in
 * backend `guide/wishlist.py`) — the form sends the days and the server
 * resolves them against the day the wish was added. The form still has to
 * show the resulting date while the person types, before any round-trip, so
 * the addition exists once here too. `shared/cooling_cases.json` is run by
 * both suites, so the date on screen is the date that gets saved.
 */
import { addDaysISO, daysBetween } from '../../../utils/dateWindow'

/** The date a cooling-off of `days` ends, counted from `addedOn`. */
export function coolingUntilFromDays(addedOn: string, days: number): string {
  return addDaysISO(addedOn, Math.max(0, days))
}

/** The days after `addedOn` that `coolingUntil` falls — negative for a date
 *  picked before the wish was added. */
export function daysAfterAdded(addedOn: string, coolingUntil: string): number {
  return daysBetween(addedOn, coolingUntil)
}

export type CoolingDaysParse = { ok: true; days: number | null } | { ok: false; error: string }

/**
 * Read a typed number of days: a whole number within the served range, or a
 * stated reason why not. Never `Number(text)`, which reads blank as 0 and
 * anything else as NaN — the settings dialog did exactly that and a cleared
 * box silently set a zero-day cooling-off on every future wish.
 *
 * `blank` decides what an empty box means, and the two callers genuinely
 * differ: a wish may have no cooling-off at all, while a setting must always
 * hold a number. That is the only difference, so it is a parameter rather
 * than a second copy.
 */
export function parseDays(
  text: string,
  {
    min = 0,
    max,
    label,
    blank,
  }: { min?: number; max: number; label: string; blank: 'null' | 'refuse' }
): CoolingDaysParse {
  const trimmed = text.trim()
  if (trimmed === '') {
    if (blank === 'null') return { ok: true, days: null }
    return { ok: false, error: `${label} needs a number from ${min} to ${max}` }
  }
  const days = /^\d+$/.test(trimmed) ? Number(trimmed) : NaN
  if (!Number.isInteger(days) || days < min || days > max) {
    return { ok: false, error: `${label} must be a whole number from ${min} to ${max}` }
  }
  return { ok: true, days }
}

/**
 * Read the typed cooling-off days. Blank is `null` — no cooling-off on an
 * edit, the settings default on creation.
 */
export function parseCoolingDays(text: string, max: number): CoolingDaysParse {
  return parseDays(text, { max, label: 'Cooling-off days', blank: 'null' })
}
