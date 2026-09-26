/**
 * How the Event Timeline reads its rows. Pure, so each rule the timeline
 * once got wrong is a one-line test instead of something you have to mount a
 * chart to see. A row's tone is `utils/activityClassTone`, shared with the
 * Guide.
 */
import { activityClassTone } from '../../../utils/activityClassTone'

/**
 * The chip beside a row's amount: what the row is, where the amount's sign
 * and the tone alone would say it wrong. Null for plain spending.
 *
 * Tone comes from the class, which says what a row means but not which way
 * the money went. A +5,000 inflow filed to a spending envelope is SPENDING by
 * class, and was drawn as a red "$5,000.00" with no chip — a purchase, when
 * it was money back. An inflow on an expense-toned class is named a Refund;
 * the amount beside it carries its sign.
 */
export function timelineChip(row: {
  amount: number
  activity_class: string | null
  activity_label: string
}): string | null {
  if (activityClassTone(row.activity_class) === 'expense' && row.amount > 0) return 'Refund'
  return row.activity_class === 'spending' ? null : row.activity_label
}

/**
 * Newest first. The server ranks by SIZE to pick the largest N; a timeline
 * draws them in DATE order. The panel said "newest first" while rendering the
 * server's ranking, so the newest row could appear anywhere.
 */
export function newestFirst<T extends { date: string }>(rows: readonly T[]): T[] {
  return [...rows].sort((a, b) => b.date.localeCompare(a.date))
}

/**
 * The largest magnitude on the page — the dot scale's top and the "Largest
 * Transaction" card. A max over the rows, not row 0: row 0 was the largest
 * only while the rows arrived in the server's size order, and a scale that
 * silently depends on the sort order is how it came to be wrong.
 */
export function largestMagnitude(rows: readonly { amount: number }[]): number {
  return rows.reduce((m, r) => Math.max(m, Math.abs(r.amount)), 0)
}

const DOT_MIN = 8
const DOT_RANGE = 14

/** A dot's diameter in px: the smallest at 8, the largest on the page at 22. */
export function dotSize(amount: number, largest: number): number {
  if (largest === 0) return DOT_MIN
  return Math.round(DOT_MIN + (Math.abs(amount) / largest) * DOT_RANGE)
}
