import type { Liability } from '../../../api/liabilities'
import type { PayoffPlanRequest } from '../../../api/guide'
import { parseAmountInput } from '../../../utils/money'

/**
 * The planner's rows: seeded from the budget's liabilities, edited in place,
 * added to by hand, and turned into a request only when every figure parses.
 *
 * Pure, so the rules that matter — which liabilities are offered, which are
 * named as excluded, and that a row that does not parse blocks the request
 * rather than booking zero — are each a one-line test.
 */

export interface PlannerRow {
  key: string
  name: string
  balance: string
  rate: string
  minimum: string
  /** Seeded from a liability (as opposed to typed). Edits are scenario
   *  inputs either way — nothing is written back. */
  fromLiability: boolean
  /** In the comparison. Unticking keeps the row and its figures on screen and
   *  leaves it out of the plan, which is how you ask "what if this one were
   *  not my problem" without retyping it afterwards. Removing the row was the
   *  only way to do that, and it took the figures with it. */
  include: boolean
}

export interface Seed {
  rows: PlannerRow[]
  /** Liabilities left out because their rate or minimum is not on record.
   *  Named, so the gap is a nudge rather than a silence. */
  excluded: string[]
}

export function seedRows(liabilities: Liability[]): Seed {
  const rows: PlannerRow[] = []
  const excluded: string[] = []
  for (const l of liabilities) {
    if (!(l.current_balance > 0)) continue
    if (l.interest_rate === null || l.minimum_payment === null) {
      excluded.push(l.name)
      continue
    }
    rows.push(rowFromLiability(l))
  }
  return { rows, excluded }
}

/**
 * One liability as a row, with whatever it knows filled in.
 *
 * Also used by the add menu, which offers the ones the seed left out — so a
 * mortgage with no APR on record arrives named and with its balance, and only
 * the missing figure is left to type. That is why the blanks are empty
 * strings rather than a refusal: a partly-known debt is still worth adding.
 */
export function rowFromLiability(l: Liability): PlannerRow {
  return {
    key: l.id,
    name: l.name,
    balance: l.current_balance > 0 ? String(l.current_balance) : '',
    rate: l.interest_rate === null ? '' : String(l.interest_rate),
    minimum: l.minimum_payment === null ? '' : String(l.minimum_payment),
    fromLiability: true,
    include: true,
  }
}

/** The liabilities not already in `rows` — what the add menu can offer. */
export function addableLiabilities(liabilities: Liability[], rows: PlannerRow[]): Liability[] {
  const present = new Set(rows.map((r) => r.key))
  return liabilities.filter((l) => !present.has(l.id))
}

let manualCounter = 0

export function blankRow(): PlannerRow {
  manualCounter += 1
  return {
    key: `manual-${manualCounter}`,
    name: '',
    balance: '',
    rate: '',
    minimum: '',
    fromLiability: false,
    include: true,
  }
}

export type RowField = 'name' | 'balance' | 'rate' | 'minimum'

export interface RowValidation {
  body: PayoffPlanRequest | null
  errors: Record<string, RowField[]>
  extraError: boolean
}

function isBlank(row: PlannerRow): boolean {
  return !row.name.trim() && !row.balance.trim() && !row.rate.trim() && !row.minimum.trim()
}

/**
 * Build the request, or say which fields stop it. An unparseable amount is
 * an error, never zero. A row left entirely blank is simply not a debt.
 */
export function rowsToRequest(rows: PlannerRow[], extra: string): RowValidation {
  const errors: Record<string, RowField[]> = {}
  const debts: PayoffPlanRequest['debts'] = []

  for (const row of rows) {
    if (isBlank(row)) continue
    // Left out on purpose: not a debt for this run, and not an error either.
    // Checked before validation so an excluded row with a half-typed figure
    // does not block the plan it is not part of.
    if (!row.include) continue
    const bad: RowField[] = []
    const balance = parseAmountInput(row.balance)
    const rate = parseAmountInput(row.rate)
    const minimum = parseAmountInput(row.minimum)
    if (!row.name.trim()) bad.push('name')
    if (Number.isNaN(balance) || balance < 0) bad.push('balance')
    if (Number.isNaN(rate) || rate < 0 || rate > 100) bad.push('rate')
    if (Number.isNaN(minimum) || minimum < 0) bad.push('minimum')
    if (bad.length) {
      errors[row.key] = bad
      continue
    }
    debts.push({
      key: row.key,
      name: row.name.trim(),
      balance: String(balance),
      annual_rate: String(rate),
      minimum_payment: String(minimum),
    })
  }

  let extraError = false
  let extraValue = '0'
  if (extra.trim()) {
    const parsed = parseAmountInput(extra)
    if (Number.isNaN(parsed) || parsed < 0) extraError = true
    else extraValue = String(parsed)
  }

  const ok = Object.keys(errors).length === 0 && !extraError && debts.length > 0
  return { body: ok ? { debts, extra: extraValue } : null, errors, extraError }
}
