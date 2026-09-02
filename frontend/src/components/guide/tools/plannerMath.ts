import type { PlanCadence, PlanPayload, PlanPaycheck } from '../../../api/categoryPlans'
import { centsToInputString } from '../../../utils/amountExpression'
import { parseAmountInput, toCents } from '../../../utils/money'

/**
 * Every figure the category planner shows, spelled once — pure, in cents.
 *
 * The server stores the document and never recomputes these: totals are
 * display derivations of stored facts (per-row cents, per-paycheck incomes),
 * so the one place they can disagree with the columns is here, and here has
 * the tests. The apply-targets classification is the opposite way round —
 * server-only — for the same one-implementation reason.
 *
 * Draft types mirror the payload with raw input strings, LoanCompare-style:
 * '' is "not entered" (a legal draft, saved as null), unparseable text is an
 * error the field must show (`Number.isNaN` on the parse result) and is
 * saved as null — never silently as zero.
 */

export interface DraftItem {
  id: string
  /** Linked budget category; null = free-form row. */
  categoryId: string | null
  name: string
  /** Raw text; '' = no due day. */
  dueDay: string
  /** Raw text; '' = not entered yet. */
  amount: string
}

export interface DraftPaycheck {
  id: string
  /** Raw text; '' = no override, the even split applies. */
  income: string
  items: DraftItem[]
}

export interface PlanDraft {
  monthlyIncome: string
  cadence: PlanCadence
  countOverride: number | null
  paychecks: DraftPaycheck[]
}

export const CADENCES: { value: PlanCadence; label: string; count: number }[] = [
  { value: 'weekly', label: 'Weekly', count: 4 },
  { value: 'biweekly', label: 'Every 2 weeks', count: 2 },
  { value: 'semimonthly', label: 'Twice a month', count: 2 },
  { value: 'monthly', label: 'Monthly', count: 1 },
]

/** The typical paychecks-per-month for a cadence — a default, not a rule.
 *  The count override is how a 3-paycheck biweekly month is expressed. */
export function derivePaycheckCount(cadence: PlanCadence): number {
  const found = CADENCES.find((c) => c.value === cadence)
  return found ? found.count : 2
}

/**
 * `total` cents across `count` paychecks, remainder cents to the earliest —
 * the sum is exactly `total`, never a cent invented or lost to rounding.
 */
export function evenSplitCents(totalCents: number, count: number): number[] {
  if (count < 1) return []
  const base = Math.floor(totalCents / count)
  const remainder = totalCents - base * count
  return Array.from({ length: count }, (_, i) => base + (i < remainder ? 1 : 0))
}

/** '' → null (not entered); unparseable or negative → NaN (show the error);
 *  otherwise integer cents. */
export function parseCentsField(text: string): number | null {
  if (!text.trim()) return null
  const parsed = parseAmountInput(text)
  return Number.isNaN(parsed) ? Number.NaN : toCents(parsed)
}

/** '' → null; anything but an integer 1–31 → NaN. */
export function parseDueDayField(text: string): number | null {
  if (!text.trim()) return null
  const n = Number(text)
  return Number.isInteger(n) && n >= 1 && n <= 31 ? n : Number.NaN
}

/** A paycheck's income: its override, or its slot in the even split. */
export function paycheckIncomeCents(payload: PlanPayload, index: number): number {
  const override = payload.paychecks[index]?.income_override_cents
  if (override !== null && override !== undefined) return override
  return evenSplitCents(payload.monthly_income_cents, payload.paychecks.length)[index] ?? 0
}

/** What this paycheck is asked to cover. Rows not yet given an amount count
 *  as nothing — they are drafts, not zeros. */
export function paycheckPlannedCents(paycheck: PlanPaycheck): number {
  return paycheck.items.reduce((sum, item) => sum + (item.amount_cents ?? 0), 0)
}

export function monthlyPlannedCents(payload: PlanPayload): number {
  return payload.paychecks.reduce((sum, p) => sum + paycheckPlannedCents(p), 0)
}

/** The sum of what the paychecks actually show — equal to the monthly
 *  take-home until an override makes them drift, which the summary says. */
export function incomeTotalCents(payload: PlanPayload): number {
  return payload.paychecks.reduce((sum, _, i) => sum + paycheckIncomeCents(payload, i), 0)
}

/**
 * What an imported category's row starts at. Only a monthly-funding target
 * translates directly to a monthly plan figure; a savings balance or a
 * weekly rhythm would need invented arithmetic, so those seed blank.
 */
export function seedCentsFromTarget(
  target: { target_type: string; target_amount: number } | null | undefined
): number | null {
  if (!target || target.target_type !== 'monthly_funding') return null
  return toCents(target.target_amount)
}

/**
 * Grow or shrink to `nextCount` paychecks. A removed paycheck's rows move to
 * the last remaining one — never dropped — and `moved` says how many, so the
 * caller can tell the user. New paychecks arrive blank; ids come from the
 * caller so this stays pure.
 */
export function resizePaychecks(
  paychecks: DraftPaycheck[],
  nextCount: number,
  mkId: () => string
): { paychecks: DraftPaycheck[]; moved: number } {
  if (nextCount === paychecks.length) return { paychecks, moved: 0 }
  if (nextCount > paychecks.length) {
    const grown = [...paychecks]
    while (grown.length < nextCount) grown.push({ id: mkId(), income: '', items: [] })
    return { paychecks: grown, moved: 0 }
  }
  const kept = paychecks.slice(0, nextCount).map((p) => ({ ...p, items: [...p.items] }))
  const orphans = paychecks.slice(nextCount).flatMap((p) => p.items)
  kept[kept.length - 1].items.push(...orphans)
  return { paychecks: kept, moved: orphans.length }
}

// ── draft ↔ payload ──────────────────────────────────────────────────────────

export function payloadToDraft(payload: PlanPayload): PlanDraft {
  return {
    monthlyIncome:
      payload.monthly_income_cents === 0 ? '' : centsToInputString(payload.monthly_income_cents),
    cadence: payload.cadence,
    countOverride: payload.paycheck_count_override,
    paychecks: payload.paychecks.map((p) => ({
      id: p.id,
      income: p.income_override_cents === null ? '' : centsToInputString(p.income_override_cents),
      items: p.items.map((i) => ({
        id: i.id,
        categoryId: i.category_id,
        name: i.name,
        dueDay: i.due_day === null ? '' : String(i.due_day),
        amount: i.amount_cents === null ? '' : centsToInputString(i.amount_cents),
      })),
    })),
  }
}

/** Invalid fields (NaN parses) serialize as null/absent — the input keeps its
 *  text and its error style; the document never records a guess for it. */
export function draftToPayload(draft: PlanDraft): PlanPayload {
  const monthly = parseCentsField(draft.monthlyIncome)
  return {
    schema_version: 1,
    monthly_income_cents: monthly === null || Number.isNaN(monthly) ? 0 : monthly,
    cadence: draft.cadence,
    paycheck_count_override: draft.countOverride,
    paychecks: draft.paychecks.map((p) => {
      const income = parseCentsField(p.income)
      return {
        id: p.id,
        income_override_cents: income === null || Number.isNaN(income) ? null : income,
        items: p.items.map((i) => {
          const cents = parseCentsField(i.amount)
          const due = parseDueDayField(i.dueDay)
          return {
            id: i.id,
            category_id: i.categoryId,
            name: i.name,
            due_day: due === null || Number.isNaN(due) ? null : due,
            amount_cents: cents === null || Number.isNaN(cents) ? null : cents,
          }
        }),
      }
    }),
  }
}
