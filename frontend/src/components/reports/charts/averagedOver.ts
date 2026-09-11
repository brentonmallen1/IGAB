/**
 * The sub-line under a card whose figure is a monthly average: what kind of
 * average, and how the served `months_averaged` bears on it.
 *
 * Cost of Living and Subscriptions each wrote this inline and had already
 * parted: "per month, over 11 complete" beside "effective, over 11 complete
 * months", and neither said "1 complete month". Naming the count is what
 * lets a reader check the figure, and what explains a young budget's low
 * one; the count is spelled here once so the two cards cannot say it two
 * ways. What the count MEANS is not the same on both, so there are two
 * sentences and one fragment: Cost of Living really does divide everything
 * by it, and Subscriptions is bounded by it.
 */

/** "11 complete months", "1 complete month" — the fragment both labels end
 *  on, so the two cards cannot disagree about the plural either. */
function completeMonths(monthsAveraged: number): string {
  return `${monthsAveraged} complete ${monthsAveraged === 1 ? 'month' : 'months'}`
}

export function averagedOver(prefix: string, monthsAveraged: number): string {
  return `${prefix}, over ${completeMonths(monthsAveraged)}`
}

/**
 * Subscriptions' own wording. Its headline is not one average over one
 * window: every service is spread over the complete months since ITS first
 * charge, and the category and summary figures are those lines added up, so
 * "effective, over 11 complete months" named a divisor no figure on the page
 * used. `months_averaged` is the most any service can divide by — a bound,
 * and said as one.
 */
export function averagedSinceEachFirstCharge(monthsAveraged: number): string {
  return `effective, each service since its first charge, at most ${completeMonths(monthsAveraged)}`
}
