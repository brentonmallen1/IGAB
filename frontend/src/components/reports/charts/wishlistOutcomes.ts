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
    { key: 'still_open', label: 'Still waiting', count: d.still_open },
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
