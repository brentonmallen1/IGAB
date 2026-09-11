import type { DateFormat, TimeFormat } from '../types'

const MONTH_NAMES_SHORT = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
]
const MONTH_NAMES_LONG = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
]

/** Get the first day of the current month as "YYYY-MM-01" */
export function currentMonthStart(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`
}

/**
 * The calendar date WRITTEN at the start of `s`, as a local Date.
 *
 * `new Date("2026-01-01")` parses a date-only string as UTC midnight, which
 * west of Greenwich is the previous day — the previous month for a month
 * start, the previous year each January. Appending "T00:00:00" forces the
 * local parse. The first ten characters are read so a datetime string
 * ("2026-09-01T00:00:00") parses too: the month formatters used to take it
 * whole, append the suffix a second time and print "undefined NaN".
 *
 * For an INSTANT (a datetime with an offset) the written date is not the
 * viewer's date; use `formatDateTimeWithOptions`, which renders it locally.
 */
export function parseLocalDate(s: string): Date {
  return new Date(s.slice(0, 10) + 'T00:00:00')
}

/** Advance month by N months, returns "YYYY-MM-01". The day goes to the 1st
 * BEFORE the month moves: from the 31st, moving first overflowed a short
 * month, so January 31 plus one month was March. */
export function addMonths(monthStr: string, delta: number): string {
  const d = parseLocalDate(monthStr)
  d.setDate(1)
  d.setMonth(d.getMonth() + delta)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
}

const pad2 = (n: number) => String(n).padStart(2, '0')

/**
 * The one day label, with or without its year. Each setting orders the parts
 * once: `mdy` "Sep 10, 2026" / "Sep 10", `dmy` "10 Sep 2026" / "10 Sep", `ymd`
 * "2026-09-10" / "09-10". Unparseable input comes back verbatim rather than as
 * "undefined NaN, NaN".
 */
function dayLabel(dateStr: string, dateFormat: DateFormat, withYear: boolean): string {
  const d = parseLocalDate(dateStr)
  if (isNaN(d.getTime())) return dateStr
  const day = d.getDate()
  const month = MONTH_NAMES_SHORT[d.getMonth()]
  const year = d.getFullYear()
  switch (dateFormat) {
    case 'mdy':
      return withYear ? `${month} ${day}, ${year}` : `${month} ${day}`
    case 'dmy':
      return withYear ? `${day} ${month} ${year}` : `${day} ${month}`
    case 'ymd': {
      const monthDay = `${pad2(d.getMonth() + 1)}-${pad2(day)}`
      return withYear ? `${year}-${monthDay}` : monthDay
    }
  }
}

/**
 * The one month label, long ("September 2026") or short ("Sep 26"). `ymd`
 * puts the year first in both; the other settings put the month first.
 */
function monthLabel(monthStr: string, dateFormat: DateFormat, short: boolean): string {
  const d = parseLocalDate(monthStr)
  if (isNaN(d.getTime())) return monthStr
  const month = (short ? MONTH_NAMES_SHORT : MONTH_NAMES_LONG)[d.getMonth()]
  const year = short ? String(d.getFullYear()).slice(-2) : String(d.getFullYear())
  return dateFormat === 'ymd' ? `${year} ${month}` : `${month} ${year}`
}

/** Format ISO date "YYYY-MM-DD" with configurable format */
export function formatDateWithOptions(dateStr: string, dateFormat: DateFormat): string {
  return dayLabel(dateStr, dateFormat, true)
}

/** Format "YYYY-MM-01" to month/year with configurable format */
export function formatMonthWithOptions(monthStr: string, dateFormat: DateFormat): string {
  return monthLabel(monthStr, dateFormat, false)
}

/**
 * Format "YYYY-MM-DD" to a short day + month, no year ("Sep 10").
 *
 * For a dense axis where the year is already established by the surrounding
 * labels. `CashProjectionReport` carried its own copy of MONTH_NAMES_SHORT to
 * do this, and sent `ymd` down the US month-first branch; `ymd` stays numeric
 * here, the year-less half of what `formatDateWithOptions` prints.
 */
export function formatDayMonthWithOptions(dateStr: string, dateFormat: DateFormat): string {
  return dayLabel(dateStr, dateFormat, false)
}

/**
 * Format "YYYY-MM-01" to a short month + 2-digit year ("Sep 26").
 *
 * The axis labels on Savings, Subscriptions and Cost of Living each spelled
 * this as `new Date(monthStr).toLocaleDateString('en-US', ...)`: a UTC parse
 * (see `parseLocalDate`) that read "Dec 25" for January 2026 west of UTC, and
 * a hard-coded 'en-US' that ignored the budget's date-format setting.
 */
export function formatMonthShortWithOptions(monthStr: string, dateFormat: DateFormat): string {
  return monthLabel(monthStr, dateFormat, true)
}

/**
 * Format a full ISO datetime (e.g. "2026-08-17T13:53:41+00:00") as local
 * date + time. Not formatDateWithOptions: that reads the calendar date WRITTEN
 * in the string, and an instant's written date is not the viewer's — it once
 * appended "T00:00:00" to the whole datetime and printed "undefined NaN, NaN".
 * Both halves come from the same local Date so an evening entry never shows
 * tomorrow's UTC date beside its local time.
 */
export function formatDateTimeWithOptions(
  isoStr: string,
  dateFormat: DateFormat,
  timeFormat: TimeFormat
): string {
  const d = new Date(isoStr)
  if (isNaN(d.getTime())) return isoStr
  const day = d.getDate()
  const month = MONTH_NAMES_SHORT[d.getMonth()]
  const year = d.getFullYear()
  const time = formatTimeWithOptions(d.getHours(), d.getMinutes(), timeFormat)
  switch (dateFormat) {
    case 'mdy':
      return `${month} ${day}, ${year} ${time}`
    case 'dmy':
      return `${day} ${month} ${year} ${time}`
    case 'ymd':
      return (
        `${year}-${String(d.getMonth() + 1).padStart(2, '0')}-` +
        `${String(day).padStart(2, '0')} ${time}`
      )
  }
}

/** Format time with configurable format */
export function formatTimeWithOptions(
  hour: number,
  minute: number,
  timeFormat: TimeFormat
): string {
  const minStr = minute.toString().padStart(2, '0')
  if (timeFormat === '24h') {
    return `${hour.toString().padStart(2, '0')}:${minStr}`
  }
  const period = hour >= 12 ? 'PM' : 'AM'
  const h12 = hour % 12 || 12
  return `${h12}:${minStr} ${period}`
}

/** Format "YYYY-MM-01" to "January 2024" - legacy API */
export function formatMonth(monthStr: string): string {
  const d = parseLocalDate(monthStr)
  return d.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
}

/** A bare day-of-month as "1st" / "2nd" / "17th" / "23rd" — for recurring
 * days that have no date attached, like a card bill's due day. */
export function ordinalDay(day: number): string {
  const rem100 = day % 100
  const rem10 = day % 10
  const suffix =
    rem100 >= 11 && rem100 <= 13
      ? 'th'
      : rem10 === 1
        ? 'st'
        : rem10 === 2
          ? 'nd'
          : rem10 === 3
            ? 'rd'
            : 'th'
  return `${day}${suffix}`
}

/** Format ISO date "YYYY-MM-DD" to "Jan 5, 2024" - legacy API */
export function formatDate(dateStr: string): string {
  const d = parseLocalDate(dateStr)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

/** A Date's LOCAL calendar day as YYYY-MM-DD.
 *
 * The one safe conversion. `d.toISOString().slice(0, 10)` is the trap: it
 * converts to UTC first, so a local midnight ahead of Greenwich lands on the
 * previous calendar day and an evening behind it lands on the next — the AI
 * chat told the server it was tomorrow every night after 8 in New York. Lint
 * refuses the trap; this is what it points to. `today()`, `yesterday()`,
 * utils/dateWindow and the search grammar all read it rather than respell it.
 */
export function toISODate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** Today's date as "YYYY-MM-DD" */
export function today(): string {
  return toISODate(new Date())
}

/** Yesterday's date as "YYYY-MM-DD" */
export function yesterday(): string {
  const d = new Date()
  d.setDate(d.getDate() - 1)
  return toISODate(d)
}
