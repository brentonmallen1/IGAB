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
    if (!(Number(l.current_balance) > 0)) continue
    if (l.interest_rate === null || l.minimum_payment === null) {
      excluded.push(l.name)
      continue
    }
    rows.push({
      key: l.id,
      name: l.name,
      balance: String(l.current_balance),
      rate: String(l.interest_rate),
      minimum: String(l.minimum_payment),
      fromLiability: true,
    })
  }
  return { rows, excluded }
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
