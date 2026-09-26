/**
 * The sub-line under a card whose figure is a monthly average: what kind of
 * average, and how the served `months_averaged` bears on it.
 *
 * Cost of Living and Subscriptions each wrote this inline and had already
 * parted: "per month, over 11 complete" beside "effective, over 11 complete
 * months", and neither said "1 complete month". Naming the count is what
 * lets a reader check the figure, and what explains a young budget's low
 * one; the count is spelled here once so the two cards cannot say it two
 * ways. (Subscriptions no longer averages at all: its Monthly is a year's
 * charges ÷ 12 — backend `domain/subscriptions.py`.)
 */

/** "11 complete months", "1 complete month" — the fragment every label ends
 *  on (and the Essentials table's note), so none can disagree about the plural. */
export function completeMonths(monthsAveraged: number): string {
  return `${monthsAveraged} complete ${monthsAveraged === 1 ? 'month' : 'months'}`
}

export function averagedOver(prefix: string, monthsAveraged: number): string {
  return `${prefix}, over ${completeMonths(monthsAveraged)}`
}
