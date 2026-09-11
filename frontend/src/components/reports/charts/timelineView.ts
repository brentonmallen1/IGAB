/**
 * How the Event Timeline reads its rows. Pure, so each rule the timeline
 * once got wrong is a one-line test instead of something you have to mount a
 * chart to see.
 */

/** The dot and amount tones `EventTimeline.css` draws. */
export type TimelineTone = 'income' | 'expense' | 'savings' | 'neutral'

const TONE_BY_CLASS: Record<string, TimelineTone> = {
  income: 'income',
  spending: 'expense',
  savings: 'savings',
  debt_principal: 'savings',
  investment_return: 'neutral',
  debt_interest: 'expense',
  transfer_internal: 'neutral',
}

/**
 * Dot colour by what a row means, not which way the amount points — so it
 * takes no amount. A transfer into savings is negative and is not an expense.
 *
 * A null class is a split whose legs disagree, and an unrecognised class is
 * one added server-side since; both get the neutral tone rather than a
 * sign-based guess. Falling back to the sign is the exact mislabelling the
 * activity taxonomy exists to end, and it is how an all-savings split came to
 * be drawn as a red expense.
 */
export function timelineTone(activityClass: string | null): TimelineTone {
  return (activityClass !== null && TONE_BY_CLASS[activityClass]) || 'neutral'
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
