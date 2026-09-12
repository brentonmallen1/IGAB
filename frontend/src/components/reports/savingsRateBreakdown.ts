/** Pure presentation for the savings-rate dialog: nothing here decides a
 *  figure. The totals, the contributors and their reasons are served by
 *  /reports/savings-contributors; the rate is the one the opening card shows. */
import { otherIncome } from './charts/incomeSourcesView'

/** The rate's formula in words. "Saved" and "Debt principal" are the labels
 *  of the figures the dialog lists beneath it, so the formula names what the
 *  reader can see. */
export function rateFormula(withDebt: boolean): string {
  return withDebt ? '(Saved + Debt principal) ÷ Income' : 'Saved ÷ Income'
}

/** How many income sources the dialog names before folding the rest. */
export const TOP_INCOME_SOURCES = 5

/**
 * The first `limit` income sources, and what the rest add up to — so the list
 * the reader sees still sums to the Income figure above it. The remainder is
 * `otherIncome`, Income by Source's "Other" band: whether a shown set is the
 * whole is one rule, read in cents, and a remainder can be negative.
 */
export function foldIncomeSources<T extends { total: number }>(
  sources: readonly T[],
  income: number,
  limit: number = TOP_INCOME_SOURCES
): { shown: T[]; rest: { count: number; total: number } | null } {
  const shown = sources.slice(0, limit)
  const folded = sources.length - shown.length
  if (folded === 0) return { shown, rest: null }
  const total = otherIncome(
    income,
    shown.map((s) => s.total)
  )
  // null means the folded sources net to nothing (they can cancel: a
  // paycheque and its clawback), not that the figure is unknown.
  return { shown, rest: { count: folded, total: total ?? 0 } }
}
