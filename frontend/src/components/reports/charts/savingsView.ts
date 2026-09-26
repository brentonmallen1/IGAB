import type { TrackingEntry } from '../../../types'
import { firstFigure } from '../../../utils/trackingStart'

/**
 * Why the Set aside line starts where it does, or null when it starts with
 * the window.
 *
 * The line is blank before anything in the section has a figure (the server
 * serves null there), where it used to draw $0 and then climb by a whole
 * account's balance the month the account was linked. A blank needs a
 * reason beside it: when accounts arrived that month, it names them.
 */
export function setAsideStartNote(
  months: string[],
  totals: (number | null)[],
  entries: TrackingEntry[][],
  formatMonthShort: (month: string) => string
): string | null {
  const first = firstFigure(totals)
  if (first === null || first === 0) return null
  const month = formatMonthShort(months[first])
  const arrived = entries[first] ?? []
  if (arrived.length === 0) return `Starts ${month}, the first month anything was set aside.`
  const names = arrived.map((e) => e.name).join(', ')
  return `Starts ${month}, when ${arrived.length === 1 ? 'its account was' : 'its accounts were'} linked: ${names}.`
}
