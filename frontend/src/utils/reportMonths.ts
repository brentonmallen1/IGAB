/**
 * The running month on a report, said one way everywhere.
 *
 * Every "N months" is the last N COMPLETE months (backend
 * `domain.dates.ReportWindow`); a report that also draws the running month
 * serves it flagged — `partial_month` — because its figures are month-to-date.
 * One "12 months" picker used to give some reports twelve complete months and
 * others eleven and the running one, and Savings Rate's headline flipped sign
 * because a few days of a new month rode in it: the bills in, the pay not yet.
 *
 * So the running month is drawn apart — lighter, and labelled "so far" — and
 * never feeds an average, a total or a headline. The label and the filter live
 * here so no chart spells either a second way.
 */

/** A served month row that says whether it is the running month. */
export interface MonthRow {
  partial_month: boolean
}

/** The rows a headline, total or average may read: the complete months. */
export function completeMonthRows<T extends MonthRow>(rows: readonly T[]): T[] {
  return rows.filter((r) => !r.partial_month)
}

/** A month's axis or table label: "Sep 26", or "Sep 26 so far" for the
 *  running month. `formatMonthShort` is `useFormatters().formatMonthShort` —
 *  the one month-label format every report reads. */
export function reportMonthLabel(
  month: string,
  partial: boolean,
  formatMonthShort: (month: string) => string
): string {
  const label = formatMonthShort(month)
  return partial ? `${label} so far` : label
}

/** How much of its colour the running month's bar keeps: present, but
 *  plainly not a finished month beside the others. */
export const RUNNING_MONTH_OPACITY = 0.4

/** "through Aug 26" — what a figure built from complete months covers,
 *  named by its last month. Null when there is none to name. */
export function throughMonth(
  lastComplete: string | null | undefined,
  formatMonthShort: (month: string) => string
): string | null {
  return lastComplete ? `through ${formatMonthShort(lastComplete)}` : null
}

/** "Jun 26 – Aug 26", or one month's label when the range is a single month —
 *  the months a figure averages. Null when there is no range to name. */
export function monthRange(
  start: string | null | undefined,
  end: string | null | undefined,
  formatMonthShort: (month: string) => string
): string | null {
  if (!start || !end) return null
  const from = formatMonthShort(start)
  const to = formatMonthShort(end)
  return from === to ? from : `${from} – ${to}`
}
