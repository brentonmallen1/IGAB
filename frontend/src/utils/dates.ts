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

/** Advance month by N months, returns "YYYY-MM-01" */
export function addMonths(monthStr: string, delta: number): string {
  const d = new Date(monthStr + 'T00:00:00')
  d.setMonth(d.getMonth() + delta)
  d.setDate(1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
}

/** Format ISO date "YYYY-MM-DD" with configurable format */
export function formatDateWithOptions(dateStr: string, dateFormat: DateFormat): string {
  const d = new Date(dateStr + 'T00:00:00')
  const day = d.getDate()
  const month = MONTH_NAMES_SHORT[d.getMonth()]
  const year = d.getFullYear()

  switch (dateFormat) {
    case 'mdy':
      return `${month} ${day}, ${year}`
    case 'dmy':
      return `${day} ${month} ${year}`
    case 'ymd':
      return dateStr
  }
}

/** Format "YYYY-MM-01" to month/year with configurable format */
export function formatMonthWithOptions(monthStr: string, dateFormat: DateFormat): string {
  const d = new Date(monthStr + 'T00:00:00')
  const month = MONTH_NAMES_LONG[d.getMonth()]
  const year = d.getFullYear()

  switch (dateFormat) {
    case 'ymd':
      return `${year} ${month}`
    default:
      return `${month} ${year}`
  }
}

/**
 * Format "YYYY-MM-DD" to a short day + month, no year ("Sep 10").
 *
 * For a dense axis where the year is already established by the surrounding
 * labels. `CashProjectionReport` carried its own copy of MONTH_NAMES_SHORT to
 * do this, and sent `ymd` down the US month-first branch; here `ymd` stays
 * numeric, matching `formatDateWithOptions`, which returns the ISO string for
 * that setting.
 */
export function formatDayMonthWithOptions(dateStr: string, dateFormat: DateFormat): string {
  const d = new Date(dateStr.slice(0, 10) + 'T00:00:00')
  const day = d.getDate()
  const month = MONTH_NAMES_SHORT[d.getMonth()]

  switch (dateFormat) {
    case 'dmy':
      return `${day} ${month}`
    case 'ymd':
      return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    default:
      return `${month} ${day}`
  }
}

/**
 * Format "YYYY-MM-01" to a short month + 2-digit year ("Sep 26").
 *
 * The axis labels on Savings, Subscriptions and Cost of Living each spelled
 * this as `new Date(monthStr).toLocaleDateString('en-US', ...)`. A date-ONLY
 * ISO string parses as UTC midnight, and toLocaleDateString renders in the
 * viewer's zone, so every label west of UTC read one month early — and one
 * YEAR early each January, where "2026-01-01" rendered "Dec 25". Appending
 * "T00:00:00" is what forces the local parse, exactly as
 * `formatMonthWithOptions` above already does; the three inline copies were
 * written without it.
 *
 * Hard-coding 'en-US' also ignored the budget's date-format setting, so the
 * `ymd` arm here matches `formatMonthWithOptions`.
 */
export function formatMonthShortWithOptions(monthStr: string, dateFormat: DateFormat): string {
  const d = new Date(monthStr.slice(0, 10) + 'T00:00:00')
  const month = MONTH_NAMES_SHORT[d.getMonth()]
  const year = String(d.getFullYear()).slice(-2)

  switch (dateFormat) {
    case 'ymd':
      return `${year} ${month}`
    default:
      return `${month} ${year}`
  }
}

/**
 * Format a full ISO datetime (e.g. "2026-08-17T13:53:41+00:00") as local
 * date + time. Not formatDateWithOptions: that takes date-ONLY strings and
 * appends "T00:00:00" — fed a datetime it produced "undefined NaN, NaN".
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
  const d = new Date(monthStr + 'T00:00:00')
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
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

/** Today's date as "YYYY-MM-DD" */
export function today(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** Yesterday's date as "YYYY-MM-DD" */
export function yesterday(): string {
  const d = new Date()
  d.setDate(d.getDate() - 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
