/** Pure view math for the Income by Source report. */
import { isPartial } from '../drillDownTotals'

/**
 * A month's income from payees outside the shown series — the "Other" band —
 * or null when there is none.
 *
 * The server quantizes each payee's month and sums the quantized figures, so
 * the true difference is a whole number of cents; what a float subtraction
 * adds is dust. Read it in cents: `rest > 0` drew a band for the dust, and
 * `rest >= 0.01` dropped a genuine cent, because 1000.01 − (600 + 400) is
 * 0.00999… in floating point. Whether the shown sources are the whole month
 * is `isPartial`, the tooltip's and the drill table's rule.
 *
 * The rest can be NEGATIVE, and that band is drawn too: a month's income can
 * carry a reconciliation adjustment filed to Ready to Assign, so the payees
 * beyond the shown series can net below zero. Dropping it left the stack
 * taller than the month the table's All row reports. The chart stacks with
 * `stackOffset="sign"`, so the band hangs below the axis instead of painting
 * over the series beneath it.
 */
export function otherIncome(monthTotal: number, shown: readonly number[]): number | null {
  const drawn = shown.reduce((sum, v) => sum + v, 0)
  const rest = monthTotal - drawn
  return isPartial(drawn, monthTotal) ? rest : null
}

/**
 * How many payees the window counts as a SOURCE of income.
 *
 * A payee whose income rows net to zero or less over the window paid the
 * household nothing: "Sources 2" for one employer plus a −$75 reconciliation
 * adjustment overstates where the money comes from. Such a payee still has
 * its table row and still counts in the total — this is the count only.
 */
export function incomeSourceCount(sources: readonly { total: number }[]): number {
  return sources.filter((s) => s.total > 0).length
}
