/**
 * When a card's bill is next due, and when that is close enough to say so.
 *
 * The stored rule has two shapes (server: `domain/payment_due.py`, which owns
 * which combinations are storable):
 *
 *  - `day_of_month` — the 17th, every month, clamped in a short one.
 *  - `cycle_days` — a fixed number of days after the last due date actually
 *    seen. An issuer billing on a 31-day cycle walks its due date through the
 *    calendar, so recording that as "the 17th" is right for one cycle and
 *    wrong from the next.
 *
 * **The arithmetic is on this side on purpose**, by CLAUDE.md's boundary rule:
 * no backend path reads a due date — amortization is monthly and dateless by
 * design, and `payment_due_day` has always been metadata — and the one input
 * beyond the stored columns is *today*, which is the client's to know. A GET
 * carries no `client_today`, so a served answer would be computed against UTC
 * and read a day early every evening west of Greenwich.
 *
 * One module because two surfaces ask: the liability page's terms header and
 * the budget page's credit-card strip. They must not answer differently.
 *
 * Nothing here knows about balances beyond the one number it is handed, and
 * nothing here claims a bill was *missed*: the app cannot see whether a
 * statement was paid, so the next due date is always today or later and the
 * copy never says "overdue".
 */

import { addDaysISO, daysBetween } from './dateWindow'
import { ordinalDay, toISODate } from './dates'

export type PaymentDueKind = 'day_of_month' | 'cycle_days'

/** The rule as the server serves it — the three columns, unchanged. */
export interface PaymentDueRule {
  payment_due_kind: PaymentDueKind
  payment_due_day: number | null
  payment_due_cycle_days: number | null
  payment_due_anchor: string | null
}

/**
 * How near a due date has to be before the app mentions it unprompted.
 *
 * A week: long enough that a household still has a pay period to move money
 * in, short enough that the indicator is not simply always on. A card billing
 * every 31 days wears it for under a quarter of its cycle.
 */
export const DUE_SOON_DAYS = 7

/** `day` of that month, clamped to the month's length — the 31st is the 28th
 *  in February, not the 3rd of March. The same clamp the server's
 *  `domain/schedule.py` applies to a monthly schedule; kept to whole local
 *  calendar components, never `new Date(str)`. */
function dayInMonth(year: number, monthIndex: number, day: number): string {
  const lastDay = new Date(year, monthIndex + 1, 0).getDate()
  return toISODate(new Date(year, monthIndex, Math.min(day, lastDay)))
}

/**
 * The next date this bill is due, today included, or null when the card has
 * no usable rule on file.
 *
 * Null is the ordinary answer, not an error: most cards have never had a due
 * date typed into them. The server refuses to STORE an incomplete cycle, so
 * in practice null means "nothing on file" — but this returns it for any
 * unevaluable rule rather than trusting that, because a row written before
 * the columns existed is exactly the shape that would otherwise render as a
 * confident wrong date.
 */
export function nextDueDate(rule: PaymentDueRule, today: string): string | null {
  if (rule.payment_due_kind === 'cycle_days') {
    const cycle = rule.payment_due_cycle_days
    const anchor = rule.payment_due_anchor
    // A cycle of zero or less never advances: the step below would not reach
    // today however many times it ran.
    if (!anchor || cycle === null || cycle <= 0) return null
    const elapsed = daysBetween(anchor, today)
    // Whole cycles from the anchor to the first one that has not passed.
    // Ceiling, so an anchor in the future steps BACKWARDS to the earliest
    // occurrence still ahead of today rather than reporting the anchor
    // itself — a user who typed next month's due date would otherwise see the
    // cycle before it silently skipped.
    return addDaysISO(anchor, Math.ceil(elapsed / cycle) * cycle)
  }

  const day = rule.payment_due_day
  if (day === null || day < 1 || day > 31) return null
  const [year, month] = today.split('-').map(Number)
  const thisMonth = dayInMonth(year, month - 1, day)
  // On the due date itself the bill is due today, not next month.
  return thisMonth >= today ? thisMonth : dayInMonth(year, month, day)
}

/**
 * The rule in words, for the field that shows when the bill comes round —
 * "the 17th of each month", "every 31 days". Null when nothing is on file.
 *
 * The recurrence, never the next date: the two are different facts and the
 * header shows both, one as the value and one as the caption under it.
 */
export function describeDueRule(rule: PaymentDueRule): string | null {
  if (rule.payment_due_kind === 'cycle_days') {
    const cycle = rule.payment_due_cycle_days
    if (!rule.payment_due_anchor || cycle === null || cycle <= 0) return null
    return `every ${cycle} days`
  }
  const day = rule.payment_due_day
  if (day === null || day < 1 || day > 31) return null
  return `the ${ordinalDay(day)} of each month`
}

/** "today" / "tomorrow" / "in 4 days" — the tail of every sentence about a
 *  due date, so they all word it the same way. */
export function dueInPhrase(days: number): string {
  if (days <= 0) return 'today'
  if (days === 1) return 'tomorrow'
  return `in ${days} days`
}

export interface DueNotice {
  /** The next due date, today or later. */
  date: string
  /** Whole days from today; 0 means today. Never negative. */
  days: number
  /** "today" / "tomorrow" / "in 4 days". */
  phrase: string
}

/**
 * The indicator: what to say when a bill is close AND the card still owes
 * something, or null when there is nothing worth interrupting anyone about.
 *
 * Both halves are required. A due date on a card carrying no balance is a
 * calendar fact nobody needs surfaced, and a balance with no due date on file
 * has nothing to be close to — the row already says what is owed.
 *
 * `owed` is POSITIVE when money is owed. The two callers hold that number in
 * opposite signs — a liability's `current_balance` is owed-positive, a card
 * row's `balance` is owed-negative — which is precisely why the conversion is
 * made at each call site against this one documented convention rather than
 * guessed at here.
 */
export function dueSoonNotice(
  rule: PaymentDueRule,
  { today, owed }: { today: string; owed: number }
): DueNotice | null {
  if (owed <= 0) return null
  const date = nextDueDate(rule, today)
  if (date === null) return null
  const days = daysBetween(today, date)
  if (days > DUE_SOON_DAYS) return null
  return { date, days, phrase: dueInPhrase(days) }
}
