import { describe, expect, it } from 'vitest'
import { FREQUENCIES, FREQ_LABELS, daysUntil, dueLabel, dueState, frequencyLabel } from './schedule'

describe('daysUntil', () => {
  it('counts forward within a month', () => {
    expect(daysUntil('2026-09-10', '2026-09-06')).toBe(4)
  })
  it('crosses a month end', () => {
    expect(daysUntil('2026-10-02', '2026-09-29')).toBe(3)
  })
  it('crosses a year end', () => {
    expect(daysUntil('2027-01-01', '2026-12-31')).toBe(1)
  })
  it('is negative once the date has passed', () => {
    expect(daysUntil('2026-09-01', '2026-09-06')).toBe(-5)
  })
  it('is zero on the day', () => {
    expect(daysUntil('2026-09-06', '2026-09-06')).toBe(0)
  })
  it('is unmoved by a DST change between the two dates', () => {
    // 8 Mar → 9 Mar 2026 is 23 local hours in the US; still one day.
    expect(daysUntil('2026-03-09', '2026-03-08')).toBe(1)
  })
})

describe('dueLabel', () => {
  it('reads today, future and overdue with correct plurals', () => {
    expect(dueLabel(0)).toBe('Due today')
    expect(dueLabel(1)).toBe('Due in 1 day')
    expect(dueLabel(3)).toBe('Due in 3 days')
    expect(dueLabel(-1)).toBe('Overdue 1 day')
    expect(dueLabel(-2)).toBe('Overdue 2 days')
  })
})

describe('dueState', () => {
  const base = { days_before_reminder: 3, auto_create: false }
  it('is due-soon at the boundary of the reminder window and inside it', () => {
    expect(dueState({ ...base, next_occurrence_date: '2026-09-09' }, '2026-09-06')).toBe(
      'due-soon'
    )
    expect(dueState({ ...base, next_occurrence_date: '2026-09-06' }, '2026-09-06')).toBe(
      'due-soon'
    )
  })
  it('is nothing one day outside the window', () => {
    expect(dueState({ ...base, next_occurrence_date: '2026-09-10' }, '2026-09-06')).toBeNull()
  })
  it('is overdue once the date has passed', () => {
    expect(dueState({ ...base, next_occurrence_date: '2026-09-05' }, '2026-09-06')).toBe(
      'overdue'
    )
  })
  it('never calls an auto-entered schedule overdue — it posts itself', () => {
    expect(
      dueState({ ...base, auto_create: true, next_occurrence_date: '2026-09-05' }, '2026-09-06')
    ).toBe('due-soon')
  })
  it('a zero-day window still flags the day itself', () => {
    expect(
      dueState(
        { days_before_reminder: 0, auto_create: false, next_occurrence_date: '2026-09-06' },
        '2026-09-06'
      )
    ).toBe('due-soon')
  })
})

describe('the cadence vocabulary', () => {
  it('FREQ_LABELS is derived from FREQUENCIES — the three copies collapsed here', () => {
    for (const f of FREQUENCIES) expect(FREQ_LABELS[f.value]).toBe(f.label)
    expect(Object.keys(FREQ_LABELS)).toHaveLength(FREQUENCIES.length)
  })
  it('knows the two cadences the old copies did not', () => {
    expect(frequencyLabel('twice_monthly')).toBe('Twice a month')
    expect(frequencyLabel('once')).toBe('Once')
  })
  it('falls back to the raw value for anything unknown', () => {
    expect(frequencyLabel('fortnightly')).toBe('fortnightly')
  })
})
