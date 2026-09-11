/** Date-window math for reports, on YYYY-MM-DD strings.
 *
 * Never parses date strings with `new Date(str)` — that treats date-only
 * strings as UTC midnight, which shifts a calendar day for anyone west of
 * Greenwich. All arithmetic goes through local-calendar components instead.
 */

// The Date → YYYY-MM-DD conversion lives in utils/dates (`toISODate`): this
// module had the one copy the reports read, beside a second name for it and
// three more spellings elsewhere in utils/.
import { toISODate, today } from './dates'

function parts(s: string): [number, number, number] {
  const [y, m, d] = s.split('-').map(Number)
  return [y, m, d]
}

/** Add (or subtract) whole days; the Date constructor normalizes the calendar. */
export function addDaysISO(s: string, days: number): string {
  const [y, m, d] = parts(s)
  return toISODate(new Date(y, m - 1, d + days))
}

/** Difference in calendar days (b - a). */
export function daysBetween(a: string, b: string): number {
  const [ay, am, ad] = parts(a)
  const [by, bm, bd] = parts(b)
  return Math.round((Date.UTC(by, bm - 1, bd) - Date.UTC(ay, am - 1, ad)) / 86_400_000)
}

/** The equal-length window immediately preceding [start, end] (both inclusive).
 * May 1–Jul 21 (82 days) → Feb 8–Apr 30. */
export function previousWindow(start: string, end: string): { start: string; end: string } {
  const lengthDays = daysBetween(start, end) + 1
  const prevEnd = addDaysISO(start, -1)
  const prevStart = addDaysISO(prevEnd, -(lengthDays - 1))
  return { start: prevStart, end: prevEnd }
}

/** First day of the month `monthsBack` months before the current one —
 * mirrors the backend's `_subtract_months(first_of_month, months - 1)`. */
export function monthsAgoStartISO(monthsBack: number): string {
  const now = new Date()
  return toISODate(new Date(now.getFullYear(), now.getMonth() - monthsBack, 1))
}

/** Full window of a "YYYY-MM" month, end clamped to today (report queries
 * never run past today, so panel totals must not either). */
export function monthWindow(month: string): { start: string; end: string } {
  const [y, m] = month.split('-').map(Number)
  const start = toISODate(new Date(y, m - 1, 1))
  const lastDay = toISODate(new Date(y, m, 0)) // day 0 of next month = last of this
  const t = today()
  return { start, end: lastDay < t ? lastDay : t }
}
