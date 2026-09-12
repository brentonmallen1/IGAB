/**
 * The client's one home for what a scheduled transaction's cadence is called
 * and when it counts as due.
 *
 * The cadence vocabulary was written three times — the editor's option list,
 * the Scheduled page's label map, the register's Upcoming rows' label map —
 * and none of the three knew about twice-monthly, so a paycheck schedule
 * rendered as the raw string `twice_monthly`. `FREQ_LABELS` is derived from
 * `FREQUENCIES` so the two cannot disagree.
 *
 * Reminders live here rather than on the server on purpose: the server never
 * acts on one (nothing is sent), and the client has every input — the next
 * date, the reminder window, and its own today. Pure so every boundary is a
 * one-line test.
 */

import type { ScheduledTransaction } from '../types'
import { daysBetween } from './dateWindow'

export const FREQUENCIES = [
  { value: 'once', label: 'Once' },
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'biweekly', label: 'Every 2 weeks' },
  { value: 'twice_monthly', label: 'Twice a month' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'yearly', label: 'Yearly' },
] as const

export type Frequency = (typeof FREQUENCIES)[number]['value']

export const FREQ_LABELS: Record<string, string> = Object.fromEntries(
  FREQUENCIES.map((f) => [f.value, f.label])
)

export function frequencyLabel(frequency: string): string {
  return FREQ_LABELS[frequency] ?? frequency
}

/** Whole days from `todayISO` to `dateISO`; negative when the date has passed.
 *  The reminder's reading of `daysBetween`, which owns the calendar-day
 *  arithmetic — this module had a second copy of it. */
export function daysUntil(dateISO: string, todayISO: string): number {
  return daysBetween(todayISO, dateISO)
}

/** "Due today", "Due in 3 days", "Overdue 2 days". */
export function dueLabel(days: number): string {
  if (days === 0) return 'Due today'
  if (days > 0) return `Due in ${days} day${days === 1 ? '' : 's'}`
  const late = -days
  return `Overdue ${late} day${late === 1 ? '' : 's'}`
}

export type DueState = 'overdue' | 'due-soon' | null

/** Overdue once the date has passed; due-soon inside the schedule's own
 *  reminder window (`days_before_reminder`, inclusive); otherwise nothing.
 *  A schedule the nightly job auto-enters is never overdue in this sense —
 *  it posts itself — so it only ever reads due-soon. */
export function dueState(
  s: Pick<ScheduledTransaction, 'next_occurrence_date' | 'days_before_reminder' | 'auto_create'>,
  todayISO: string
): DueState {
  const days = daysUntil(s.next_occurrence_date, todayISO)
  if (days < 0) return s.auto_create ? 'due-soon' : 'overdue'
  if (days <= s.days_before_reminder) return 'due-soon'
  return null
}

export function isDueSoon(
  s: Pick<ScheduledTransaction, 'next_occurrence_date' | 'days_before_reminder' | 'auto_create'>,
  todayISO: string
): boolean {
  return dueState(s, todayISO) !== null
}
