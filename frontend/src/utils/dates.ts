import type { DateFormat, TimeFormat } from '../types'

const MONTH_NAMES_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const MONTH_NAMES_LONG = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

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

/** Format time with configurable format */
export function formatTimeWithOptions(hour: number, minute: number, timeFormat: TimeFormat): string {
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
