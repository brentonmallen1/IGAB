/**
 * Do a split's legs add up to its parent?
 *
 * Three editors asked this — the mobile quick-add sheet, the desktop
 * transaction editor, and the inline split editor — and each answered it
 * twice: once to enable Save, and again ten lines later to render "Remaining".
 * Six spellings of one question. They had drifted:
 *
 *  - Only the quick-add sheet required the parent amount to be positive, so
 *    the desktop editor's Save button was enabled with an empty amount and
 *    wrote a $0.00 transaction with no lines.
 *  - `splits.every(...)` is true for an empty array, so "no legs at all"
 *    counted as valid everywhere.
 *  - The desktop editor picked which amount field to validate with string
 *    truthiness (`outflow || inflow`, where "0" wins) while its submit handler
 *    picked numerically, so a "0" outflow with a "50" inflow validated against
 *    0 and saved 50.
 *
 * Integer cents throughout: summing legs as floats rejects valid splits like
 * 0.10 + 0.20. Legs are magnitudes, as all three editors hold them — the
 * parent's sign is applied structurally at submit — so this compares
 * magnitudes. The backend compares signed values, and the two agree because
 * every leg is required to be positive here.
 *
 * The exact-equality rule is shared with the backend through
 * `shared/split_cases.json`, which both this module's tests and
 * `backend/tests/unit/test_split_predicate.py` run against.
 *
 * One case the fixture keeps backend-only: `Transaction.amount` is
 * `Numeric(19,4)`, so the server can hold and must reject a sub-cent leg,
 * while the editors round to the nearest cent at input — long before this
 * function sees the value. Do not widen this module to four decimal places
 * to close that gap; the rounding is upstream.
 */
import { centsToInputString, expressionToCents } from './amountExpression'

export interface SplitLegInput {
  amount: string
  categoryId: string | null
}

export type SplitReason =
  | 'ok'
  | 'no-total'
  | 'no-legs'
  | 'under-assigned'
  | 'over-assigned'
  | 'missing-category'
  | 'non-positive-leg'

export interface SplitCheck {
  /** The parent's magnitude in cents. */
  totalCents: number
  /** The legs' sum in cents. */
  assignedCents: number
  /** Signed: positive means still to assign, negative means over. */
  remainingCents: number
  isValid: boolean
  reason: SplitReason
}

/**
 * @param totalCents the parent's magnitude in integer cents. Callers must
 *   derive this the same way they derive the amount they submit — validating
 *   one field and saving another is how the "0"/"50" bug happened.
 */
export function checkSplit(totalCents: number, legs: SplitLegInput[]): SplitCheck {
  const assignedCents = legs.reduce((sum, leg) => {
    const cents = expressionToCents(leg.amount)
    return sum + (isNaN(cents) ? 0 : cents)
  }, 0)
  const remainingCents = totalCents - assignedCents

  const base = { totalCents, assignedCents, remainingCents }
  const invalid = (reason: SplitReason): SplitCheck => ({ ...base, isValid: false, reason })

  if (!Number.isFinite(totalCents) || totalCents <= 0) return invalid('no-total')
  if (legs.length === 0) return invalid('no-legs')

  for (const leg of legs) {
    const cents = expressionToCents(leg.amount)
    if (isNaN(cents) || cents <= 0) return invalid('non-positive-leg')
    if (!leg.categoryId) return invalid('missing-category')
  }

  if (remainingCents > 0) return invalid('under-assigned')
  if (remainingCents < 0) return invalid('over-assigned')

  return { ...base, isValid: true, reason: 'ok' }
}

/** Drafts for a split's saved lines, for either split editor. The server ids
 *  ride along so a save updates the lines in place (PUT …/splits) instead
 *  of replacing them. */
export function draftsFromLines(
  lines: { id: string; amount: number | string; category_id: string | null; memo: string | null }[]
): { tempId: string; serverId: string; amount: string; categoryId: string | null; memo: string }[] {
  return lines.map((line) => ({
    tempId: line.id,
    serverId: line.id,
    amount: String(Math.abs(Number(line.amount))),
    categoryId: line.category_id,
    memo: line.memo ?? '',
  }))
}

/**
 * Which leg "fill the rest" writes to: the first one with no amount yet.
 * Null when there is nothing to fill — the split is done or over — or no
 * leg is empty, where writing into a typed leg would overwrite a figure a
 * person entered.
 */
export function remainderTarget(
  legs: readonly SplitLegInput[],
  remainingCents: number
): number | null {
  if (!Number.isFinite(remainingCents) || remainingCents <= 0) return null
  const i = legs.findIndex((leg) => isBlank(leg.amount))
  return i === -1 ? null : i
}

/** The legs with what is left written into `remainderTarget`'s leg, as the
 *  editors hold amounts (magnitude strings). Unchanged when there is none. */
export function fillRemainder<T extends SplitLegInput>(legs: T[], remainingCents: number): T[] {
  const i = remainderTarget(legs, remainingCents)
  if (i === null) return legs
  return legs.map((leg, j) =>
    j === i ? { ...leg, amount: centsToInputString(remainingCents) } : leg
  )
}

/**
 * "Cover the rest": put everything still unassigned into `categoryId`.
 *
 * A category already on a leg takes it on that leg — two Groceries lines is
 * a split nobody meant to make. Otherwise it goes on a blank leg (no
 * category, no amount) if there is one, else on a new leg from `newLeg`.
 * Unchanged when nothing is left to cover.
 */
export function coverRemainder<T extends SplitLegInput>(
  legs: T[],
  remainingCents: number,
  categoryId: string,
  newLeg: () => T
): T[] {
  if (!Number.isFinite(remainingCents) || remainingCents <= 0) return legs
  const plus = (leg: T): T => {
    const had = expressionToCents(leg.amount)
    return {
      ...leg,
      categoryId,
      amount: centsToInputString((isNaN(had) ? 0 : had) + remainingCents),
    }
  }
  const same = legs.findIndex((leg) => leg.categoryId === categoryId)
  if (same !== -1) return legs.map((leg, i) => (i === same ? plus(leg) : leg))
  const blank = legs.findIndex((leg) => leg.categoryId === null && isBlank(leg.amount))
  if (blank !== -1) return legs.map((leg, i) => (i === blank ? plus(leg) : leg))
  return [...legs, plus({ ...newLeg(), amount: '' })]
}

function isBlank(amount: string): boolean {
  const cents = expressionToCents(amount)
  return amount.trim() === '' || isNaN(cents) || cents === 0
}
