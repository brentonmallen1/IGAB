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
    assigned += b.assigned
    activity += b.activity
    available += b.available
  }
  return { assigned, activity, available, carriedOver: available - assigned - activity }
}

/**
 * How much overspending there is, and how much of it is card debt.
 *
 * Three surfaces ask this — the hero chip, the Assign dropdown's Cover row,
 * and the cover dialog — and until 2026-09-05 two of them answered it with
 * `total_overspent_cash` while the third acted on the whole red. Covering
 * therefore emptied the chip and the row while the grid stayed red, which is
 * the app disagreeing with itself about whether there is work to do.
 *
 * So the question has one implementation, over the shape both payloads share
 * (`BudgetMonth` and the assign-strategy totals both carry these two fields).
 * The headline is the WHOLE red: Cover Overspending funds all of it, and the
 * card part is a label on where the money lands — into a card's set-aside,
 * retiring debt — not a smaller offer.
 */
export interface OverspendingSource {
  total_overspent: number
  total_overspent_credit: number
}

export interface Overspending {
  /** The figure every call to action shows. Matches the grid's red. */
  total: number
  /** The part of `total` that rode onto a card. A subset, never a second
   *  number beside it — so the header does not show it at all; the cards
   *  band says it, as card debt, where assigning to the card retires it. */
  onCards: number
}

export function overspending(source: OverspendingSource | undefined | null): Overspending {
  return {
    total: Number(source?.total_overspent ?? 0),
    onCards: Number(source?.total_overspent_credit ?? 0),
  }
}

export interface LastMonthSource {
  name: string
  amount: number
}

export interface OverspentLastMonth {
  total: number
  /** The largest few, named — the header reads top-down. */
  sources: LastMonthSource[]
  /** How many more envelopes contributed beyond `sources`. */
  more: number
}

/**
 * What the 1st took out of Ready to Assign, for the header's one line.
 *
 * Composition of served facts only: the server decides each amount
 * (`overspent_last_month`); this names them and keeps the line short. Ready
 * to Assign always dropped by this total on the 1st, and until this line
 * existed nothing on the page said why. Null when nothing was absorbed.
 */
export function overspentLastMonth(
  items: { category_id: string; amount: number }[] | undefined,
  nameOf: (categoryId: string) => string,
  shown = 3
): OverspentLastMonth | null {
  if (!items || items.length === 0) return null
  const sources = items.map((i) => ({ name: nameOf(i.category_id), amount: Number(i.amount) }))
  return {
    total: sources.reduce((sum, s) => sum + s.amount, 0),
    sources: sources.slice(0, shown),
    more: Math.max(0, sources.length - shown),
  }
}
