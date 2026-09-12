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
 * Read the typed days. Blank is `null` — no cooling-off on an edit, the
 * settings default on creation. Anything else must be a whole number from 0
 * to the served limit, and anything that is not says so: never read as 0.
 */
export function parseCoolingDays(text: string, max: number): CoolingDaysParse {
  const trimmed = text.trim()
  if (trimmed === '') return { ok: true, days: null }
  const days = /^\d+$/.test(trimmed) ? Number(trimmed) : NaN
  if (!Number.isInteger(days) || days > max) {
    return { ok: false, error: `Cooling-off days must be a whole number from 0 to ${max}` }
  }
  return { ok: true, days }
}
