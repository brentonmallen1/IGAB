/**
 * The Income vs Expenses table's totals row. Presentation only: every figure
 * is a served month's, summed.
 */
import type { IncomeExpenseMonth } from '../../../types'
import { fromCents, sumToCents } from '../../../utils/money'
import { completeMonthRows } from '../../../utils/reportMonths'

/** The columns the table sums. */
export type IncomeExpenseFigure = 'income' | 'expenses' | 'savings' | 'debt_principal' | 'net'

export interface IncomeExpenseTotals extends Record<IncomeExpenseFigure, number> {
  /** The first and last month summed — what the row's label names. */
  first: string
  last: string
}

/**
 * The window's totals: the complete months only, summed in cents.
 *
 * The running month is a row of the table (labelled "so far") but never part
 * of the total (`utils/reportMonths.ts`): its pay and bills are still
 * arriving, and the picker's "12 months" is twelve complete ones. Null when
 * there is no complete month to add up.
 */
export function windowTotals(rows: readonly IncomeExpenseMonth[]): IncomeExpenseTotals | null {
  const complete = completeMonthRows(rows)
  if (complete.length === 0) return null
  const sum = (key: IncomeExpenseFigure) => fromCents(sumToCents(complete.map((m) => m[key])))
  return {
    income: sum('income'),
    expenses: sum('expenses'),
    savings: sum('savings'),
    debt_principal: sum('debt_principal'),
    net: sum('net'),
    first: complete[0].month,
    last: complete[complete.length - 1].month,
  }
}
