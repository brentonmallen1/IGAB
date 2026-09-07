import { MAX_FUNDING_DAY } from '../../utils/targets'
/**
 * The target form's vocabulary and its validation rules.
 *
 * Two components render this form — the standalone editor and the inspector
 * section — and both carried their own copy of the type list and the payload
 * construction, including the same bug: `parseFloat(amount) || 0`.
 *
 * That is wrong twice. `parseFloat` mis-reads the separator conventions
 * `utils/money` explicitly supports (`parseFloat("1.234,56")` is `1.234`), and
 * `|| 0` turns anything it cannot read into a zero target — which can never be
 * underfunded, so the row silently stops asking for money. Both files sit next
 * to comments elsewhere in the budget code stating the rule this broke:
 * unparseable input must never quietly write $0.
 *
 * Three shapes. "Needed for spending" was a fourth that computed as one of
 * these two — monthly when undated, savings-by-date when dated — and its
 * helper text could not say how it differed, because it did not.
 */
import { parseAmountInput } from '../../utils/money'

export const TARGET_TYPES = [
  {
    value: 'monthly_funding',
    label: 'Monthly funding',
    help: 'Assign this much every month.',
  },
  {
    value: 'weekly_funding',
    label: 'Weekly funding',
    help: 'Assign this much every week — the month asks for four or five, by how many of that day it has.',
  },
  {
    value: 'savings_balance',
    label: 'Savings balance',
    help: 'Keep this much available. Add a date to spread the saving over the months until then.',
  },
] as const

export type TargetTypeValue = (typeof TARGET_TYPES)[number]['value']

export const WEEKDAYS = [
  { value: 0, label: 'Monday' },
  { value: 1, label: 'Tuesday' },
  { value: 2, label: 'Wednesday' },
  { value: 3, label: 'Thursday' },
  { value: 4, label: 'Friday' },
  { value: 5, label: 'Saturday' },
  { value: 6, label: 'Sunday' },
] as const

export function targetTypeLabel(value: string): string {
  return TARGET_TYPES.find((t) => t.value === value)?.label ?? value
}

export interface TargetPayload {
  target_type: string
  target_amount: number
  target_date: string | null
  check_after_day: number | null
  weekday: number | null
}

export interface TargetFormFields {
  targetType: string
  amount: string
  targetDate: string
  /** '' for none; the select's value otherwise. */
  weekday: string
  /** '' for "use the budget's funding day". */
  checkAfterDay: string
}

export type TargetFormResult = { ok: true; payload: TargetPayload } | { ok: false; error: string }

type Parsed<T> = { ok: true; value: T } | { ok: false; error: string }

/** '' means "none"; anything else must name a weekday 0..6. */
function parseWeekday(raw: string): Parsed<number | null> {
  if (raw === '') return { ok: true, value: null }
  const n = Number(raw)
  if (!Number.isInteger(n) || n < 0 || n > 6) {
    return { ok: false, error: 'Pick the day of the week this target funds.' }
  }
  return { ok: true, value: n }
}

/** '' means "use the budget's funding day"; otherwise a day 1..28. */
function parseCheckAfterDay(raw: string): Parsed<number | null> {
  if (raw === '') return { ok: true, value: null }
  const n = Number(raw)
  if (!Number.isInteger(n) || n < 1 || n > MAX_FUNDING_DAY) {
    return { ok: false, error: `The check-after day must be between 1 and ${MAX_FUNDING_DAY}.` }
  }
  return { ok: true, value: n }
}

/** Build the upsert payload, or say why it cannot be built. A weekly target
 *  needs its weekday; only a savings balance carries a date (the form drops
 *  a stale one rather than sending it to be refused). */
export function buildTargetPayload(fields: TargetFormFields): TargetFormResult {
  const parsed = parseAmountInput(fields.amount)
  if (isNaN(parsed)) return { ok: false, error: 'Enter an amount.' }
  if (parsed <= 0) return { ok: false, error: 'A target has to be more than zero.' }
  const isWeekly = fields.targetType === 'weekly_funding'
  const weekday = parseWeekday(fields.weekday)
  if (!weekday.ok) return weekday
  if (isWeekly && weekday.value === null) {
    return { ok: false, error: 'Pick the day of the week this target funds.' }
  }
  const checkAfterDay = parseCheckAfterDay(fields.checkAfterDay)
  if (!checkAfterDay.ok) return checkAfterDay
  const isSavings = fields.targetType === 'savings_balance'
  return {
    ok: true,
    payload: {
      target_type: fields.targetType,
      target_amount: parsed,
      target_date: isSavings && fields.targetDate ? fields.targetDate : null,
      check_after_day: checkAfterDay.value,
      weekday: isWeekly ? weekday.value : null,
    },
  }
}
