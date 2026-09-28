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
 * One module because three surfaces ask: the app-wide banner
 * (`CardDueBanner`), the budget page's credit-card strip and the liability
 * page's terms header. They must not answer differently, so all three read
 * `reminderForCard` → `cardDueReminder`.
 *
 * **The reminder rule** (`cardDueReminder`), only while the card owes money:
 *
 *  - *Paid* means a payment dated AFTER the previous due date. A bill due on
 *    the 3rd and paid on the 29th of the month before is paid; a payment ON
 *    a due date paid that bill, not the next one.
 *  - *Due*: the next due date is within `DUE_SOON_DAYS` and nothing has been
 *    paid since the last one.
 *  - *Past due*: the most recent due date before today went by with nothing
 *    paid since the due date before it. It stays until a payment lands (or
 *    the banner is dismissed), and it wins over *due*. It is never claimed
 *    for a due date before the account joined the budget (`dueWatchStart`):
 *    a card configured today is not overdue today.
 *
 * *A payment* is what the server serves as `last_payment_date`: the latest
 * transfer leg onto the card from one of the budget's cash accounts
 * (`CARD_PAYMENT_FROM_CASH`), dated today or earlier. Refunds and money from
 * off-budget accounts are not payments. The known limit: a payment whose
 * checking leg never paired as a transfer is invisible here, which is why
 * the banner can be dismissed and says "no payment seen" rather than "unpaid".
 * The date is served because only the server can see the ledger; the rule
 * stays here because no backend path decides it.
 */

import { isCardAccount, type AccountKindFields } from './accountKinds'
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
 * The most recent due date strictly BEFORE `date` — one step back from
 * `nextDueDate` in either shape. Null exactly when `nextDueDate` is.
 *
 * Strictly before, so on a due date itself the answer is the one before it:
 * that is what lets the reminder ask "the due date before this one" by
 * passing a due date in.
 */
export function previousDueDate(rule: PaymentDueRule, date: string): string | null {
  if (rule.payment_due_kind === 'cycle_days') {
    const next = nextDueDate(rule, date)
    const cycle = rule.payment_due_cycle_days
    // nextDueDate is on or after `date` and is the FIRST such occurrence, so
    // one cycle earlier is before it.
    return next === null || cycle === null ? null : addDaysISO(next, -cycle)
  }

  const day = rule.payment_due_day
  if (day === null || day < 1 || day > 31) return null
  const [year, month] = date.split('-').map(Number)
  const thisMonth = dayInMonth(year, month - 1, day)
  // Anchored to the stored day, like the step forward: a bill on the 31st is
  // the 28th in February and the 31st again in January.
  return thisMonth < date ? thisMonth : dayInMonth(year, month - 2, day)
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

export type CardDueState = 'due' | 'past_due'

/** A bill worth interrupting someone about. */
export interface CardDueReminder {
  state: CardDueState
  /** `due`: the next due date, today or later. `past_due`: the most recent
   *  due date that went by with nothing paid — the date the reminder is
   *  about, and the one its dismissal is keyed on. */
  dueDate: string
  /** Whole days from today to `dueDate`: 0..DUE_SOON_DAYS when due, negative
   *  when past due. */
  days: number
  /** A payment dated after this would have counted — the due date before
   *  `dueDate`'s bill. "No payment seen since" is said of this date. */
  paidAfter: string
}

export interface CardDueInputs {
  today: string
  /** POSITIVE when money is owed — a liability's `current_balance`. */
  owed: number
  /** The latest payment onto the card, today or earlier (served as
   *  `last_payment_date`); null when the ledger holds none. */
  lastPaymentDate: string | null
  /** The first day a missed bill can be claimed (`dueWatchStart`); null when
   *  the account is not known, which claims from any date. */
  budgetStart: string | null
}

/**
 * Whether a card's bill is due, past due, or not worth mentioning — the one
 * rule every surface reads (see the header of this file for it in words).
 *
 * Both halves are required for anything to be said: a due date on a card
 * carrying no balance is a calendar fact nobody needs surfaced, and a balance
 * with no due date on file has nothing to be due.
 */
export function cardDueReminder(
  rule: PaymentDueRule,
  { today, owed, lastPaymentDate, budgetStart }: CardDueInputs
): CardDueReminder | null {
  if (owed <= 0) return null
  const next = nextDueDate(rule, today)
  const last = previousDueDate(rule, today)
  if (next === null || last === null) return null
  // ISO dates compare as strings; a payment ON `since` paid the bill due that
  // day, so only a later one counts toward the bill after it.
  const paidSince = (since: string) => lastPaymentDate !== null && lastPaymentDate > since

  const beforeLast = previousDueDate(rule, last)
  const watched = budgetStart === null || last >= budgetStart
  if (beforeLast !== null && watched && !paidSince(beforeLast)) {
    return {
      state: 'past_due',
      dueDate: last,
      days: daysBetween(today, last),
      paidAfter: beforeLast,
    }
  }

  const days = daysBetween(today, next)
  if (days <= DUE_SOON_DAYS && !paidSince(last)) {
    return { state: 'due', dueDate: next, days, paidAfter: last }
  }
  return null
}

/**
 * The first day a card's missed bill can be claimed: the day the account
 * joined the budget, or — for the many accounts nobody has asked that — the
 * day it was added to the app, as a local date. A card added today is not
 * overdue today, whatever its due day says. Null without the account.
 */
export function dueWatchStart(
  account: { budget_start_date: string | null; created_at: string } | undefined
): string | null {
  if (!account) return null
  return account.budget_start_date ?? toISODate(new Date(account.created_at))
}

/** The served fields `reminderForCard` reads off a liability. */
export type CardDueLiability = PaymentDueRule & {
  current_balance: number
  last_payment_date: string | null
}

/** The served fields `reminderForCard` reads off the liability's account. */
export type CardDueAccount = AccountKindFields & {
  budget_start_date: string | null
  created_at: string
}

/**
 * The reminder for one card, from its liability and its account — the one
 * wiring of `cardDueReminder`'s inputs, so the banner, the strip and the
 * terms header hand it the same balance, payment and start date.
 *
 * Only for an on-budget card (`isCardAccount`), and null without the
 * account. Those are the accounts whose payments the server can see
 * (`last_payment_date` is served from `CARD_PAYMENT_FROM_CASH`, which lands
 * only on them); anywhere else no payment would ever count, and every due
 * date would read as missed forever.
 *
 * `current_balance`, not the budget month's card row: the row is the ledger
 * through the month being VIEWED, and a reminder is about now.
 */
export function reminderForCard(
  liability: CardDueLiability,
  account: CardDueAccount | undefined,
  today: string
): CardDueReminder | null {
  if (!account || !isCardAccount(account)) return null
  return cardDueReminder(liability, {
    today,
    owed: liability.current_balance,
    lastPaymentDate: liability.last_payment_date,
    budgetStart: dueWatchStart(account),
  })
}

/** "due in 4 days" / "due today" / "past due since Oct 3" — the reminder as
 *  the tail of a sentence that starts with the card's name. */
export function reminderWords(r: CardDueReminder, formatDay: (iso: string) => string): string {
  return r.state === 'past_due'
    ? `past due since ${formatDay(r.dueDate)}`
    : `due ${dueInPhrase(r.days)}`
}

/** The strip's chip: short, because it shares a line with the card's name. */
export function reminderChip(r: CardDueReminder): string {
  return r.state === 'past_due' ? 'Past due' : `Due ${dueInPhrase(r.days)}`
}
