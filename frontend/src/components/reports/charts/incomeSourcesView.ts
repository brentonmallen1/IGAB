/** Pure view math for the Income by Source report. Its stack is Spending
 *  Trends' (`stackTrends`), Other band and all. */
import type { TrendRow } from './spendingTrends'

/** The chart-row key of the income that came with no payee. */
export const NO_PAYEE_KEY = '__none__'

/** The served sources as the shared stack's rows, keyed by payee id — never
 *  by name, which two payees can share. */
export function incomeSourceRows(
  sources: readonly {
    payee_id: string | null
    payee_name: string
    monthly: number[]
    total: number
  }[]
): TrendRow[] {
  return sources.map((s) => ({
    key: s.payee_id ?? NO_PAYEE_KEY,
    name: s.payee_name,
    group_name: null,
    monthly: s.monthly,
    total: s.total,
  }))
}

/**
 * How many payees the window counts as a SOURCE of income.
 *
 * A payee whose income rows net to zero or less over the window paid the
 * household nothing: "Sources 2" for one employer plus a −$75 reconciliation
 * adjustment overstates where the money comes from. Such a payee still has
 * its table row and still counts in the total — this is the count only.
 */
export function incomeSourceCount(sources: readonly { total: number }[]): number {
  return sources.filter((s) => s.total > 0).length
}
