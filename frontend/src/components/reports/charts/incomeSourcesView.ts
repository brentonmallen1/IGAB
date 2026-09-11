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
 * 0.00999… in floating point. Negative dust (the shown sources summing a
 * hair over the total) is not an income source either. Whether the shown
 * sources are the whole month is `isPartial`, the tooltip's and the drill
 * table's rule.
 */
export function otherIncome(monthTotal: number, shown: readonly number[]): number | null {
  const drawn = shown.reduce((sum, v) => sum + v, 0)
  const rest = monthTotal - drawn
  return rest > 0 && isPartial(drawn, monthTotal) ? rest : null
}
