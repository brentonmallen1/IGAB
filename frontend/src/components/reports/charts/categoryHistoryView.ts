/** Pure presentation for Category History: every figure is served. */
import { CHART_COLORS, COLOR_NEGATIVE } from './chartColors'

/** A Spent bar's colour, by the month's state: red only when the envelope
 *  ended the month overspent (its served `available` below zero — the budget
 *  page's own red). Assigned was green and Spent red in every month, so a
 *  category that never once overspent drew as twelve red bars. */
export function historySpentColor(available: number | null): string {
  return available !== null && available < 0 ? COLOR_NEGATIVE : CHART_COLORS[0]
}
