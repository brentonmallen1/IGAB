/**
 * formatDateTimeWithOptions is the only formatter that accepts a full ISO
 * datetime. The Activity page used to feed one into the date-only formatter,
 * which appended 'T00:00:00' to it and rendered "undefined NaN, NaN".
 *
 * Inputs here are offset-less ISO strings, which JS parses as LOCAL time —
 * that keeps the expected local date/time fixed no matter which timezone the
 * test runner is in.
 */
import { describe, expect, it } from 'vitest'
import {
  addMonths,
  formatDateTimeWithOptions,
  formatDateWithOptions,
  formatDayMonthWithOptions,
  formatMonthShortWithOptions,
  formatMonthWithOptions,
  ordinalDay,
  parseLocalDate,
} from './dates'
import type { DateFormat } from '../types'
import { pinTimeZone } from '../test-utils/timeZone'

const AFTERNOON = '2026-08-17T13:53:41'

describe('formatDateTimeWithOptions', () => {
  it('formats mdy with 12h time', () => {
    expect(formatDateTimeWithOptions(AFTERNOON, 'mdy', '12h')).toBe('Aug 17, 2026 1:53 PM')
  })

  it('formats dmy with 24h time', () => {
    expect(formatDateTimeWithOptions(AFTERNOON, 'dmy', '24h')).toBe('17 Aug 2026 13:53')
  })

  it('formats ymd from date parts, not by echoing the input', () => {
    // The date-only formatter's ymd branch returns its input verbatim; fed a
    // datetime that would leak the raw ISO string into the UI.
    expect(formatDateTimeWithOptions(AFTERNOON, 'ymd', '24h')).toBe('2026-08-17 13:53')
  })

  it('handles midnight in both time formats', () => {
    const midnight = '2026-01-05T00:00:00'
    expect(formatDateTimeWithOptions(midnight, 'mdy', '12h')).toBe('Jan 5, 2026 12:00 AM')
    expect(formatDateTimeWithOptions(midnight, 'mdy', '24h')).toBe('Jan 5, 2026 00:00')
  })

  it('handles noon in 12h format', () => {
    expect(formatDateTimeWithOptions('2026-01-05T12:00:00', 'mdy', '12h')).toBe(
      'Jan 5, 2026 12:00 PM'
    )
  })

  it('accepts a timezone offset and stays internally consistent', () => {
    // Whatever the runner's timezone, both halves must come from the same
    // local rendering of the instant — the regression here was a date from
    // one parse and a time from another.
    const out = formatDateTimeWithOptions('2026-08-17T13:53:41+00:00', 'ymd', '24h')
    const d = new Date('2026-08-17T13:53:41+00:00')
    const expected =
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-` +
      `${String(d.getDate()).padStart(2, '0')} ` +
      `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
    expect(out).toBe(expected)
    expect(out).not.toMatch(/NaN|undefined/)
  })

  it('returns unparseable input verbatim instead of NaN soup', () => {
    expect(formatDateTimeWithOptions('not-a-date', 'mdy', '12h')).toBe('not-a-date')
  })
})

describe('ordinalDay', () => {
  it('speaks English about every day a bill can be due', () => {
    expect(ordinalDay(1)).toBe('1st')
    expect(ordinalDay(2)).toBe('2nd')
    expect(ordinalDay(3)).toBe('3rd')
    expect(ordinalDay(4)).toBe('4th')
    // The teens are the trap: 11th/12th/13th, never 11st/12nd/13rd.
    expect(ordinalDay(11)).toBe('11th')
    expect(ordinalDay(12)).toBe('12th')
    expect(ordinalDay(13)).toBe('13th')
    expect(ordinalDay(21)).toBe('21st')
    expect(ordinalDay(22)).toBe('22nd')
    expect(ordinalDay(23)).toBe('23rd')
    expect(ordinalDay(31)).toBe('31st')
  })
})

/**
 * These two pin a timezone on purpose, because the bug they cover is invisible
 * in UTC. `months` arrives from the server as a date-only string ("2026-09-01",
 * `months: list[date]`), and `new Date(dateOnly)` parses that as UTC midnight.
 * Rendered in a zone behind Greenwich it lands on the previous day — which for
 * a month-start string is the previous MONTH, and each January the previous
 * YEAR. Savings, Subscriptions and Cost of Living each hand-rolled the label
 * that way and read "Dec 25" for January 2026.
 *
 * The suite pins no zone of its own, so a UTC runner would have passed the bug.
 */
describe('short formatters are timezone-proof', () => {
  pinTimeZone('America/Los_Angeles')

  it('keeps a month-start string in its own month behind Greenwich', () => {
    // The January case is the loud one: this read "Dec 25" before the fix.
    expect(formatMonthShortWithOptions('2026-01-01', 'mdy')).toBe('Jan 26')
    expect(formatMonthShortWithOptions('2026-09-01', 'mdy')).toBe('Sep 26')
    expect(formatMonthShortWithOptions('2026-12-01', 'mdy')).toBe('Dec 26')
  })

  it('honours the ymd date setting instead of hard-coding en-US', () => {
    expect(formatMonthShortWithOptions('2026-09-01', 'ymd')).toBe('26 Sep')
    // dmy shares the month-first short form; only ymd reorders.
    expect(formatMonthShortWithOptions('2026-09-01', 'dmy')).toBe('Sep 26')
  })

  it('keeps a day-month label on its own day, and keeps ymd numeric', () => {
    expect(formatDayMonthWithOptions('2026-01-01', 'mdy')).toBe('Jan 1')
    expect(formatDayMonthWithOptions('2026-01-01', 'dmy')).toBe('1 Jan')
    expect(formatDayMonthWithOptions('2026-01-01', 'ymd')).toBe('01-01')
  })
})

describe('short formatters ahead of Greenwich', () => {
  pinTimeZone('Pacific/Auckland')

  it('reads the same month on the other side of the world', () => {
    // Proves the fix is zone-independent rather than merely shifted the other
    // way: a UTC-midnight parse is correct here, so only a local parse can
    // satisfy both this block and the one above.
    expect(formatMonthShortWithOptions('2026-01-01', 'mdy')).toBe('Jan 26')
    expect(formatMonthShortWithOptions('2026-09-01', 'mdy')).toBe('Sep 26')
  })
})

/**
 * The local date-only parse was written seven times in dates.ts: five as
 * `new Date(s + 'T00:00:00')` and the two short formatters' copies with a
 * `.slice(0, 10)` in front. Handed a datetime, the unsliced five appended the
 * suffix a second time — `formatMonthWithOptions('2026-09-01T00:00:00')` read
 * "undefined NaN" while its short sibling read "Sep 26". `parseLocalDate` is
 * the one copy, pinned behind Greenwich where a UTC parse would show.
 */
describe('parseLocalDate', () => {
  pinTimeZone('America/Los_Angeles')

  it('keeps a date-only string on its own calendar day', () => {
    const d = parseLocalDate('2026-01-01')
    expect([d.getFullYear(), d.getMonth(), d.getDate()]).toEqual([2026, 0, 1])
  })

  it('reads the date written at the front of a datetime string', () => {
    const d = parseLocalDate('2026-09-01T00:00:00')
    expect([d.getFullYear(), d.getMonth(), d.getDate()]).toEqual([2026, 8, 1])
  })

  it('reaches every formatter, so a datetime no longer prints NaN in the long ones', () => {
    // The long month and day formatters were the unsliced copies.
    expect(formatMonthWithOptions('2026-09-01T00:00:00', 'mdy')).toBe('September 2026')
    expect(formatDateWithOptions('2026-09-10T00:00:00', 'mdy')).toBe('Sep 10, 2026')
    expect(addMonths('2026-02-01T00:00:00', 1)).toBe('2026-03-01')
  })

  it('moves a month from the 31st without overflowing a short month', () => {
    // addMonths moved the month before resetting the day: Jan 31 → "Feb 31"
    // → March 3, so one month on from January 31 was March.
    expect(addMonths('2026-01-31', 1)).toBe('2026-02-01')
    expect(addMonths('2026-03-31', -1)).toBe('2026-02-01')
  })

  it('returns unparseable input verbatim instead of NaN soup', () => {
    expect(formatMonthWithOptions('not-a-month', 'mdy')).toBe('not-a-month')
    expect(formatDateWithOptions('not-a-date', 'dmy')).toBe('not-a-date')
  })
})

/**
 * The short formatters were copies of their long siblings with a different
 * name table, and their agreement on each setting's ORDER was only claimed in
 * docstrings. Each pair is one implementation now; these check the short form
 * is the long form's own parts, per setting, so the orders cannot part.
 */
describe('short and long formatters agree on every date setting', () => {
  const SETTINGS: DateFormat[] = ['mdy', 'dmy', 'ymd']

  it.each(SETTINGS)('%s: the month label orders year and month the same way', (fmt) => {
    const long = formatMonthWithOptions('2026-09-01', fmt)
    const short = formatMonthShortWithOptions('2026-09-01', fmt)
    const yearFirst = fmt === 'ymd'
    expect(long).toBe(yearFirst ? '2026 September' : 'September 2026')
    expect(short).toBe(yearFirst ? '26 Sep' : 'Sep 26')
  })

  it.each([
    ['mdy', 'Sep 10, 2026', 'Sep 10'],
    ['dmy', '10 Sep 2026', '10 Sep'],
    ['ymd', '2026-09-10', '09-10'],
  ] as const)('%s: the day label is the dated one without its year', (fmt, long, short) => {
    expect(formatDateWithOptions('2026-09-10', fmt)).toBe(long)
    expect(formatDayMonthWithOptions('2026-09-10', fmt)).toBe(short)
  })

  it('ymd prints the written date, not the datetime it was handed', () => {
    // The dated ymd arm echoed its input, so a datetime leaked into the UI.
    expect(formatDateWithOptions('2026-09-10T00:00:00', 'ymd')).toBe('2026-09-10')
  })
})
