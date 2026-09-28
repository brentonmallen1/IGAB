import { describe, expect, it } from 'vitest'
import {
  DUE_SOON_DAYS,
  cardDueReminder,
  describeDueRule,
  dueInPhrase,
  dueWatchStart,
  nextDueDate,
  previousDueDate,
  reminderChip,
  reminderForCard,
  reminderWords,
  type PaymentDueRule,
} from './paymentDue'

const dayRule = (day: number | null): PaymentDueRule => ({
  payment_due_kind: 'day_of_month',
  payment_due_day: day,
  payment_due_cycle_days: null,
  payment_due_anchor: null,
})

const cycleRule = (cycle: number | null, anchor: string | null): PaymentDueRule => ({
  payment_due_kind: 'cycle_days',
  payment_due_day: null,
  payment_due_cycle_days: cycle,
  payment_due_anchor: anchor,
})

describe('a bill due on a day of the month', () => {
  it('lands on that day this month when it has not passed', () => {
    expect(nextDueDate(dayRule(17), '2026-09-10')).toBe('2026-09-17')
  })

  it('counts the due date itself as due today, not next month', () => {
    expect(nextDueDate(dayRule(17), '2026-09-17')).toBe('2026-09-17')
  })

  it('rolls to next month once the day has passed', () => {
    expect(nextDueDate(dayRule(17), '2026-09-18')).toBe('2026-10-17')
  })

  it('clamps to a short month rather than overflowing into the next', () => {
    // The 31st in February is the 28th — not the 3rd of March, which is what
    // stepping a Date past the month end produces.
    expect(nextDueDate(dayRule(31), '2026-02-10')).toBe('2026-02-28')
  })

  it('clamps to the 29th in a leap February', () => {
    expect(nextDueDate(dayRule(31), '2028-02-10')).toBe('2028-02-29')
  })

  it('goes back to the full day the month after a clamp', () => {
    // Anchored to the stored day, never to the clamped date: stepping from
    // the 28th would drift a bill on the 31st to the 28th for good.
    expect(nextDueDate(dayRule(31), '2026-03-01')).toBe('2026-03-31')
  })

  it('crosses the year end', () => {
    expect(nextDueDate(dayRule(3), '2026-12-15')).toBe('2027-01-03')
  })

  it('has no answer when no day is on file', () => {
    expect(nextDueDate(dayRule(null), '2026-09-10')).toBeNull()
  })

  it('has no answer for a day no month has', () => {
    // A row written before these columns existed, or hand-edited: render
    // nothing rather than a confident wrong date.
    expect(nextDueDate(dayRule(40), '2026-09-10')).toBeNull()
  })
})

describe('a bill due on a fixed-length cycle', () => {
  it('walks whole cycles forward from the anchor', () => {
    // 3 Sep + 31 days = 4 Oct. The whole point: a 31-day cycle does not sit
    // on the 3rd, and recording it as "the 3rd" is wrong from here on.
    expect(nextDueDate(cycleRule(31, '2026-09-03'), '2026-09-20')).toBe('2026-10-04')
  })

  it('counts the anchor itself as due when today is the anchor', () => {
    expect(nextDueDate(cycleRule(31, '2026-09-03'), '2026-09-03')).toBe('2026-09-03')
  })

  it('takes the next cycle the day after one falls due', () => {
    expect(nextDueDate(cycleRule(31, '2026-09-03'), '2026-09-04')).toBe('2026-10-04')
  })

  it('walks many cycles for an anchor months old', () => {
    // 3 Sep 2026 + 11 × 31 days = 10 Aug 2027. Eleven months on, the bill
    // has walked from the 3rd to the 10th — which is the whole reason this
    // rule cannot be stored as a day of the month.
    expect(nextDueDate(cycleRule(31, '2026-09-03'), '2027-08-01')).toBe('2027-08-10')
  })

  it('steps back to the earliest cycle still ahead when the anchor is in the future', () => {
    // A user typing NEXT month's due date should not have the cycle between
    // now and then silently skipped.
    // The cycle before the anchor is 3 Sep, already past on the 20th, so the
    // anchor itself is the answer — but on the 1st it is not.
    expect(nextDueDate(cycleRule(31, '2026-10-04'), '2026-09-20')).toBe('2026-10-04')
    expect(nextDueDate(cycleRule(31, '2026-10-04'), '2026-09-01')).toBe('2026-09-03')
  })

  it('crosses a daylight-saving change without losing a day', () => {
    // 28 days from 25 Oct 2026 is 22 Nov, through the US and EU clock
    // changes. Counted in UTC (daysBetween), so no 23-hour day rounds wrong.
    expect(nextDueDate(cycleRule(28, '2026-10-25'), '2026-11-01')).toBe('2026-11-22')
  })

  it('has no answer without an anchor to count from', () => {
    expect(nextDueDate(cycleRule(31, null), '2026-09-20')).toBeNull()
  })

  it('has no answer for a cycle that never advances', () => {
    // A zero-day step would otherwise never reach today.
    expect(nextDueDate(cycleRule(0, '2026-09-03'), '2026-09-20')).toBeNull()
  })
})

describe('the rule in words', () => {
  it('names the day for a monthly bill', () => {
    expect(describeDueRule(dayRule(17))).toBe('the 17th of each month')
  })

  it('names the cycle for a cycle bill', () => {
    expect(describeDueRule(cycleRule(31, '2026-09-03'))).toBe('every 31 days')
  })

  it('says nothing when nothing is on file', () => {
    expect(describeDueRule(dayRule(null))).toBeNull()
    expect(describeDueRule(cycleRule(31, null))).toBeNull()
  })
})

describe('how far away it reads', () => {
  it('words each distance once, so every surface says it the same way', () => {
    expect(dueInPhrase(0)).toBe('today')
    expect(dueInPhrase(1)).toBe('tomorrow')
    expect(dueInPhrase(4)).toBe('in 4 days')
  })

  it('never reads as a past date', () => {
    // A bill that has gone by is `past_due`, which has its own words
    // (`reminderWords`); this phrase is only ever asked about a date ahead.
    // Say "today" rather than "in -2 days" if a caller gets that wrong.
    expect(dueInPhrase(-2)).toBe('today')
  })
})

describe('the due date before today', () => {
  it('is earlier this month once the day has gone by', () => {
    expect(previousDueDate(dayRule(17), '2026-09-20')).toBe('2026-09-17')
  })

  it('is last month on the due date itself: today has not gone by yet', () => {
    expect(previousDueDate(dayRule(17), '2026-09-17')).toBe('2026-08-17')
  })

  it("is last month while this month's is still ahead", () => {
    expect(previousDueDate(dayRule(17), '2026-09-10')).toBe('2026-08-17')
  })

  it('crosses the year end backwards', () => {
    expect(previousDueDate(dayRule(3), '2027-01-02')).toBe('2026-12-03')
  })

  it('clamps a short month on the way back, as it does going forward', () => {
    expect(previousDueDate(dayRule(31), '2026-03-15')).toBe('2026-02-28')
    // One step back from the clamped date is January's full 31st, not the
    // 28th: stepping is anchored to the stored day, never the clamped date.
    expect(previousDueDate(dayRule(31), '2026-02-28')).toBe('2026-01-31')
  })

  it('is one cycle back from the next one on a cycle bill', () => {
    // Next is 4 Oct (3 Sep + 31), so the one before it is the anchor.
    expect(previousDueDate(cycleRule(31, '2026-09-03'), '2026-09-20')).toBe('2026-09-03')
    // On the anchor itself the anchor is due today, so the one before is a
    // whole cycle earlier.
    expect(previousDueDate(cycleRule(31, '2026-09-03'), '2026-09-03')).toBe('2026-08-03')
  })

  it('has no answer when no usable rule is on file', () => {
    expect(previousDueDate(dayRule(null), '2026-09-10')).toBeNull()
    expect(previousDueDate(cycleRule(31, null), '2026-09-10')).toBeNull()
    expect(previousDueDate(cycleRule(0, '2026-09-03'), '2026-09-10')).toBeNull()
  })
})

describe('cardDueReminder', () => {
  // Sapphire Visa: due on the 3rd, owing $412.
  const at = (
    today: string,
    over: { owed?: number; lastPaymentDate?: string | null; budgetStart?: string | null } = {}
  ) =>
    cardDueReminder(dayRule(3), {
      today,
      owed: 412,
      lastPaymentDate: null,
      budgetStart: null,
      ...over,
    })

  it('no balance: says nothing about a card that owes nothing, even with a bill gone by', () => {
    expect(at('2026-09-30', { owed: 0 })).toBeNull()
    expect(at('2026-10-05', { owed: 0 })).toBeNull()
    // A credit balance owes less than nothing.
    expect(at('2026-09-30', { owed: -50 })).toBeNull()
  })

  it('paid before the window: a payment since the last due date quiets the next one', () => {
    // Paid 20 Sep, after the 3 Sep due date; on 30 Sep the 3 Oct bill is
    // three days out and already paid.
    expect(at('2026-09-30', { lastPaymentDate: '2026-09-20' })).toBeNull()
  })

  it('paid on the 29th for the 3rd: a payment the month before counts', () => {
    // "Paid in that month", made right at the month edge: the 29th of
    // September is after the last due date (3 Sep), so the 3 Oct bill is paid
    // — before it, on it, and the day after it.
    expect(at('2026-10-01', { lastPaymentDate: '2026-09-29' })).toBeNull()
    expect(at('2026-10-03', { lastPaymentDate: '2026-09-29' })).toBeNull()
    expect(at('2026-10-04', { lastPaymentDate: '2026-09-29' })).toBeNull()
  })

  it('a payment ON a due date paid that bill, not the next one', () => {
    expect(at('2026-09-30', { lastPaymentDate: '2026-09-03' })).toEqual({
      state: 'due',
      dueDate: '2026-10-03',
      days: 3,
      paidAfter: '2026-09-03',
    })
  })

  it('due in 7 vs 8 days: speaks up on the last day of the window, not the day before', () => {
    // Last paid 20 Aug — September's bill is paid, October's is not.
    const paidAug = { lastPaymentDate: '2026-08-20' }
    expect(at('2026-09-25', paidAug)).toBeNull()
    expect(at('2026-09-26', paidAug)).toEqual({
      state: 'due',
      dueDate: '2026-10-03',
      days: DUE_SOON_DAYS,
      paidAfter: '2026-09-03',
    })
  })

  it('says due today on the due date itself, not past due', () => {
    expect(at('2026-10-03', { lastPaymentDate: '2026-08-20' })).toMatchObject({
      state: 'due',
      dueDate: '2026-10-03',
      days: 0,
    })
  })

  it('past due by one day: the day after a due date with no payment since the one before', () => {
    expect(at('2026-10-04', { lastPaymentDate: '2026-08-20' })).toEqual({
      state: 'past_due',
      dueDate: '2026-10-03',
      days: -1,
      paidAfter: '2026-09-03',
    })
  })

  it('stays past due until something is paid', () => {
    expect(at('2026-10-20', { lastPaymentDate: '2026-08-20' })).toMatchObject({
      state: 'past_due',
      dueDate: '2026-10-03',
    })
  })

  it('past due, then paid late: the late payment clears it', () => {
    // 3 Oct went by unpaid; a payment on 6 Oct is after 3 Sep, so it counts.
    expect(at('2026-10-06', { lastPaymentDate: '2026-10-06' })).toBeNull()
    expect(at('2026-10-20', { lastPaymentDate: '2026-10-06' })).toBeNull()
  })

  it('past due wins over due when the next bill is also close', () => {
    // Every 5 days from 1 Sep: 21, 26 Sep, 1 Oct. On 27 Sep the 26th went by
    // with nothing since the 21st, and 1 Oct is four days out.
    const reminder = cardDueReminder(cycleRule(5, '2026-09-01'), {
      today: '2026-09-27',
      owed: 412,
      lastPaymentDate: '2026-09-20',
      budgetStart: null,
    })
    expect(reminder).toMatchObject({ state: 'past_due', dueDate: '2026-09-26' })
  })

  it('cycle-based due: counts payment_due_cycle_days from the anchor', () => {
    const rule = cycleRule(31, '2026-09-03')
    const on = (today: string, lastPaymentDate: string) =>
      cardDueReminder(rule, { today, owed: 412, lastPaymentDate, budgetStart: null })
    // 3 Sep + 31 = 4 Oct; on 1 Oct that is three days out, and nothing has
    // been paid since 3 Sep.
    expect(on('2026-10-01', '2026-08-30')).toEqual({
      state: 'due',
      dueDate: '2026-10-04',
      days: 3,
      paidAfter: '2026-09-03',
    })
    // Paid 10 Sep, after the 3 Sep due date: the 4 Oct bill is quiet.
    expect(on('2026-10-01', '2026-09-10')).toBeNull()
    // 4 Oct went by with nothing since 3 Sep.
    expect(on('2026-10-05', '2026-08-30')).toMatchObject({
      state: 'past_due',
      dueDate: '2026-10-04',
      paidAfter: '2026-09-03',
    })
  })

  it('due date before budget start: a newly configured card is not overdue on day one', () => {
    // The card joined the budget on 20 Sep with no payments in the ledger.
    // 3 Sep is before that, so the app has no business calling it missed.
    expect(at('2026-09-20', { budgetStart: '2026-09-20' })).toBeNull()
    // The next bill still speaks up as it comes close…
    expect(at('2026-09-28', { budgetStart: '2026-09-20' })).toMatchObject({
      state: 'due',
      dueDate: '2026-10-03',
    })
    // …and is past due once it goes by unpaid.
    expect(at('2026-10-04', { budgetStart: '2026-09-20' })).toMatchObject({
      state: 'past_due',
      dueDate: '2026-10-03',
    })
    // A due date ON the budget start is inside the budget.
    expect(at('2026-09-04', { budgetStart: '2026-09-03' })).toMatchObject({
      state: 'past_due',
      dueDate: '2026-09-03',
    })
  })

  it('says nothing for a card with no due date on file', () => {
    expect(
      cardDueReminder(dayRule(null), {
        today: '2026-10-04',
        owed: 412,
        lastPaymentDate: null,
        budgetStart: null,
      })
    ).toBeNull()
  })
})

describe('where watching for a missed bill starts', () => {
  it('is the day the account joined the budget, when someone said so', () => {
    expect(
      dueWatchStart({ budget_start_date: '2026-09-20', created_at: '2026-01-05T15:00:00Z' })
    ).toBe('2026-09-20')
  })

  it('is the day the account was added, as a local date, when nobody did', () => {
    const created = new Date(2026, 8, 20, 9, 30).toISOString()
    expect(dueWatchStart({ budget_start_date: null, created_at: created })).toBe('2026-09-20')
  })

  it('is unknown without the account', () => {
    expect(dueWatchStart(undefined)).toBeNull()
  })
})

describe('reminderForCard', () => {
  const liability = {
    ...dayRule(3),
    current_balance: 412,
    last_payment_date: '2026-08-20',
  }
  const card = {
    on_budget: true,
    classification: 'liability' as const,
    budget_start_date: null,
    created_at: '2026-01-05T15:00:00Z',
  }

  it("reads the liability's owed-positive balance and served payment date", () => {
    expect(reminderForCard(liability, card, '2026-10-04')).toMatchObject({
      state: 'past_due',
      dueDate: '2026-10-03',
    })
    expect(reminderForCard({ ...liability, current_balance: 0 }, card, '2026-10-04')).toBeNull()
  })

  it('takes the start from the account, so a card added today is not overdue today', () => {
    const added = { ...card, created_at: new Date(2026, 9, 4, 8, 0).toISOString() }
    expect(reminderForCard(liability, added, '2026-10-04')).toBeNull()
  })

  it('says nothing where no payment could ever be seen', () => {
    // An off-budget card's payments are not CARD_PAYMENT_FROM_CASH, so
    // `last_payment_date` stays null there and every bill would read missed.
    expect(reminderForCard(liability, { ...card, on_budget: false }, '2026-10-04')).toBeNull()
    expect(reminderForCard(liability, undefined, '2026-10-04')).toBeNull()
  })
})

describe('the words for a reminder', () => {
  const fmt = (iso: string) => `<${iso}>`

  it('says how far off a due bill is', () => {
    const due = { state: 'due', dueDate: '2026-10-03', days: 4, paidAfter: '2026-09-03' } as const
    expect(reminderWords(due, fmt)).toBe('due in 4 days')
    expect(reminderChip(due)).toBe('Due in 4 days')
    expect(reminderWords({ ...due, days: 0 }, fmt)).toBe('due today')
  })

  it('names the date a past-due bill fell due', () => {
    const past = {
      state: 'past_due',
      dueDate: '2026-10-03',
      days: -2,
      paidAfter: '2026-09-03',
    } as const
    expect(reminderWords(past, fmt)).toBe('past due since <2026-10-03>')
    expect(reminderChip(past)).toBe('Past due')
  })
})
