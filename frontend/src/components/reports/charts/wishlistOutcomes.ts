/** What happened to each wish, as the rows of the Wishlist report's table.
 *
 * The rows are a PARTITION of every wish — each lands in exactly one — so
 * they must sum to the wish count. They did not: `dropped_early` was served
 * and summed into "decided", but no row showed it, so a wish abandoned on day
 * three vanished from the table and the rows came up one short per early
 * drop. Listing the buckets once, here, is what the partition test reads. */
import type { WishlistDisciplineReport } from '../../../types'

export interface WishlistOutcome {
  key: string
  label: string
  count: number
}

export function wishlistOutcomes(d: WishlistDisciplineReport): WishlistOutcome[] {
  const rows: WishlistOutcome[] = [
    {
      key: 'cooled_then_dropped',
      label: 'Waited, then decided against',
      count: d.cooled_then_dropped,
    },
    {
      key: 'dropped_early',
      label: 'Decided against before the wait was up',
      count: d.dropped_early,
    },
    { key: 'cooled_then_bought', label: 'Waited, then bought', count: d.cooled_then_bought },
    { key: 'bought_early', label: 'Bought before the wait was up', count: d.bought_early },
    // Open wishes, split by whether the wait is over: one past it is waiting
    // on a decision, not on the calendar, and "Still waiting" said neither.
    { key: 'still_cooling', label: 'Still in the wait', count: d.still_cooling },
    { key: 'ready_to_decide', label: 'Wait over, ready to decide', count: d.ready_to_decide },
  ]
  // Shown only when there are some, rather than folded into a bucket they
  // might not belong in: wishes with no waiting period, or ones that ended
  // before the app recorded when.
  if (d.unplaced > 0) {
    rows.push({
      key: 'unplaced',
      label: 'Ended, but not against a waiting period',
      count: d.unplaced,
    })
  }
  return rows
}

/** Every wish, whatever became of it. */
export function wishCount(d: WishlistDisciplineReport): number {
  return wishlistOutcomes(d).reduce((sum, r) => sum + r.count, 0)
}

/** "1 wish", "3 wishes". The card said "1 talked yourself out of". */
export function wishes(n: number): string {
  return `${n} ${n === 1 ? 'wish' : 'wishes'}`
}

/**
 * A money card's sub-line: how many wishes its figure sums, and how many of
 * them waited the period out — the same two facts, in the same words, under
 * Resisted and Bought. Resisted's said "N talked yourself out of" while
 * Bought's said "N after waiting", so an early drop read as the wait's doing
 * on one card and the other card could not be compared with it.
 */
export function afterTheWait(count: number, waitedOut: number): string {
  return `${wishes(count)} · ${waitedOut} after the wait`
}

/** The headline: of the wishes decided, the share that waited the period out.
 *  "60%" — whole percent, as a habit is read — or "—" with nothing decided. */
export function waitedOutShare(share: number | null): string {
  return share === null ? '—' : `${Math.round(share * 100)}%`
}

/** "24d · your wait is 30 days": the average wait read against the person's
 *  own waiting period, which is what makes it mean anything. */
export function averageWaitSub(avgDays: number | null, coolingDays: number): string {
  const period = `your wait is ${coolingDays} ${coolingDays === 1 ? 'day' : 'days'}`
  return avgDays === null ? `nothing bought yet · ${period}` : `to buy · ${period}`
}
