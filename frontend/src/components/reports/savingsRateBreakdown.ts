/** Pure presentation for the savings-rate dialog: nothing here decides a
 *  figure. The totals, the contributors and their reasons are served by
 *  /reports/savings-contributors; the rate is the one the opening card shows. */
import { DEBT_PAYMENTS, SAVED } from '../../utils/flowLabels'
import { otherBand } from './drillDownTotals'

/** The rate's formula in words. Its terms are the labels of the figures the
 *  dialog lists beneath it (`flowLabels`), so the formula names what the
 *  reader can see. */
export function rateFormula(withDebt: boolean): string {
  return withDebt ? `(${SAVED} + ${DEBT_PAYMENTS}) ÷ Income` : `${SAVED} ÷ Income`
}

/** What "Saved" is made of (backend `domain/savings.py`) — one sentence for
 *  every report surface that shows the figure. */
export const SAVED_DEFINITION =
  'Saved = moved to savings + held in Savings envelopes that count while money is in the budget.'

/** What no savings rate here can see — said on every surface that shows one.
 *  A household whose payroll splits a slice straight to savings, or defers
 *  into a 401(k), saves every month and can read a negative rate: the money
 *  never passed through an account the budget tracks, so it was never income
 *  and never saved. */
export const INVISIBLE_SAVING =
  'Saving that never passes through your budget — part of a paycheck split straight to a savings account, a 401(k) deferral taken before pay lands — is invisible here: it was never income and never saved, so a household saving that way can read a low or even negative rate.'

/** How many income sources the dialog names before folding the rest. */
export const TOP_INCOME_SOURCES = 5

/**
 * The first `limit` income sources, and what the rest add up to — so the list
 * the reader sees still sums to the Income figure above it. The remainder is
 * `otherBand`, Income by Source's "Other" band: whether a shown set is the
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
  const total = otherBand(
    income,
    shown.map((s) => s.total)
  )
  // null means the folded sources net to nothing (they can cancel: a
  // paycheque and its clawback), not that the figure is unknown.
  return { shown, rest: { count: folded, total: total ?? 0 } }
}
