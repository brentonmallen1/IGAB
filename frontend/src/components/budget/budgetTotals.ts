/**
 * Summing a set of category balances, and the one inversion that comes with it.
 *
 * Carried-over money is not a field the server sends — it is what `available`
 * exceeds this month's `assigned` plus `activity`. Two panels in the category
 * inspector derived it, under near-identical labels ("Left Over from Last
 * Month" / "Cash Left Over From Last Month"), from different sources:
 * `AvailableBreakdown` summed all three terms from the balances it was handed,
 * while `MonthSummary` subtracted the server's month totals from a
 * client-summed available.
 *
 * Those disagree by whatever the server excludes from `total_assigned` /
 * `total_activity` but includes in `category_balances` — system groups, hidden
 * categories, credit-card payment categories. All of it landed in "left over".
 *
 * One function, one source: the inversion is only meaningful over a single set
 * of balances, so it takes one. An income row (null assigned/available — no
 * envelope money) contributes nothing: its activity is income received, and
 * counting it here put every dollar earned into "left over from last month".
 */
import type { CategoryBalance } from '../../types'

export interface BalanceTotals {
  assigned: number
  activity: number
  available: number
  /** available − assigned − activity: what came in from previous months. */
  carriedOver: number
}

export function sumBalances(balances: CategoryBalance[]): BalanceTotals {
  let assigned = 0
  let activity = 0
  let available = 0
  for (const b of balances) {
    if (b.assigned === null || b.available === null) continue
    assigned += Number(b.assigned)
    activity += Number(b.activity)
    available += Number(b.available)
  }
  return { assigned, activity, available, carriedOver: available - assigned - activity }
}
