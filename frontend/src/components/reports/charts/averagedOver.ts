/**
 * The sub-line under a card whose figure is a monthly average: what kind of
 * average, and over how many complete months — the served `months_averaged`.
 *
 * Cost of Living and Subscriptions each wrote this inline and had already
 * parted: "per month, over 11 complete" beside "effective, over 11 complete
 * months", and neither said "1 complete month". Naming the count is what
 * lets a reader check the figure, and what explains a young budget's low
 * one; it is said here once so the two cards cannot say it two ways.
 */
export function averagedOver(prefix: string, monthsAveraged: number): string {
  return `${prefix}, over ${monthsAveraged} complete ${monthsAveraged === 1 ? 'month' : 'months'}`
}
