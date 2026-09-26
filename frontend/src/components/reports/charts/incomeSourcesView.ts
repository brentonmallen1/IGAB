/** Pure view math for the Income by Source report. Its Other band is
 *  `drillDownTotals.otherBand`, which Spending Trends draws too. */

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
