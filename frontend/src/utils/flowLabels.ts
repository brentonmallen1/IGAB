/**
 * The names the money-flow figures go by — on every report, card, chart,
 * dialog and Guide page that shows them.
 *
 * One figure, the transfer into a tracked debt (`debt_principal` on the
 * wire), had six names: "Debt Paid Down" on the Savings Rate card, "Debt
 * Paid" in the chart under it, "Debt principal" in its dialog and the Guide,
 * "Debt Payments" on the Cash Flow Sankey, and "(with debt)" on the rate that
 * adds it. A reader could only assume they were six figures. It is **Debt
 * payments**: the whole transfer, which on a mortgage or car loan carries
 * interest and escrow as well as principal — so "principal" and "paid down"
 * both claimed more than the figure knows.
 *
 * "Saved" is a flow — what went into savings over a window. The Savings
 * report's balance is not "Saved"; it is what is set aside.
 */

export const DEBT_PAYMENTS = 'Debt payments'

export const SAVED = 'Saved'

/** Saved with debt payments added — the numerator of the rate that counts
 *  them, and Income vs Expenses' kept-money stack. Never called "Saved" on
 *  its own: Saved is the figure without them, everywhere. */
export const SAVED_WITH_DEBT = 'Saved + debt payments'

/** A savings rate's name, with debt payments or without. The rate without
 *  them is the default everywhere it is shown. */
export function savingsRateLabel(withDebt: boolean): string {
  return withDebt ? 'Savings rate with debt payments' : 'Savings rate'
}
