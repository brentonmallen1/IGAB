import { describe, expect, it } from 'vitest'
import {
  DUE_SOON_DAYS,
  describeDueRule,
  dueInPhrase,
  dueSoonNotice,
  nextDueDate,
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
    // nextDueDate is always today or later, so a negative can only arrive
    // from a caller that computed its own date. Say "today" rather than
    // "in -2 days"; the app cannot see whether a statement was paid and must
    // not imply it was missed.
    expect(dueInPhrase(-2)).toBe('today')
  })
})

describe('the indicator', () => {
  const owing = { today: '2026-09-13', owed: 1240 }

  it('speaks up when the bill is close and the card owes something', () => {
    const notice = dueSoonNotice(dayRule(17), owing)
    expect(notice).toEqual({ date: '2026-09-17', days: 4, phrase: 'in 4 days' })
  })

  it('stays quiet on a card that owes nothing', () => {
    // A due date on a settled card is a calendar fact nobody needs surfaced.
    expect(dueSoonNotice(dayRule(17), { today: '2026-09-13', owed: 0 })).toBeNull()
  })

  it('stays quiet on a card holding a credit balance', () => {
    expect(dueSoonNotice(dayRule(17), { today: '2026-09-13', owed: -50 })).toBeNull()
  })

  it('stays quiet while the bill is still far off', () => {
    expect(dueSoonNotice(dayRule(17), { today: '2026-09-01', owed: 1240 })).toBeNull()
  })

  it('speaks up on the last day of the window and not the day before it', () => {
    const rule = dayRule(17)
    const onTheEdge = dueSoonNotice(rule, { today: '2026-09-10', owed: 1240 })
    expect(onTheEdge?.days).toBe(DUE_SOON_DAYS)
    expect(dueSoonNotice(rule, { today: '2026-09-09', owed: 1240 })).toBeNull()
  })

  it('says today on the due date itself', () => {
    const notice = dueSoonNotice(dayRule(17), { today: '2026-09-17', owed: 1240 })
    expect(notice).toEqual({ date: '2026-09-17', days: 0, phrase: 'today' })
  })

  it('says nothing for a card with no due date on file', () => {
    expect(dueSoonNotice(dayRule(null), owing)).toBeNull()
  })

  it('works the same way for a cycle bill', () => {
    const notice = dueSoonNotice(cycleRule(31, '2026-09-03'), { today: '2026-10-01', owed: 1240 })
    expect(notice).toEqual({ date: '2026-10-04', days: 3, phrase: 'in 3 days' })
  })
})
