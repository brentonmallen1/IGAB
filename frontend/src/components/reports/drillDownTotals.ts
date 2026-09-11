/** A set of rows and the whole it was taken from: the rules, in one place.
 *
 * `DrillDownTable`'s `total` prop was a free-form number with no relation to
 * `rows`, and two of its callers handed it a WIDER set: Budget vs Actual
 * passed the period's whole spend while "Overspent only" was ticked, and
 * Payee Analysis passed every payee's total beside its top-20 slice. So the
 * row headed Total was larger than the column above it — the one number on
 * the table a reader can check on paper.
 *
 * The rule: **the total is the sum of the rows it sits under.** A wider set
 * is context beside it, never the rows' own figure.
 */

export interface WiderSet {
  /** The whole set's total — the figure the rows are a part of. */
  total: number
  /** How many things are in that whole set, when it is known. */
  count?: number
  /** Plural noun for those things: "payees", "categories". */
  label?: string
}

export interface DrillDownFooter {
  /** Sum of the rows shown. Always the figure under the Total heading. */
  shown: number
  /** What heads `shown`: plain "Total" for a whole set, and "Total of the N
   *  shown" when the rows are only part of one. */
  totalLabel: string
  /** The wider set's total, or null when the rows ARE the whole set. */
  wider: number | null
  /** What to call the wider figure: "of $9,850 across 312 payees". */
  widerLabel: string | null
  /** The shown rows' share of the wider total, 0–100, or null. */
  share: number | null
}

/** Money differences below this are rounding, not a truncated set. */
const CENT = 0.005

/** Whether `shown` is only part of `whole`, rather than the whole of it with
 *  a rounding cent between them.
 *
 *  Server-rounded per-row figures routinely differ from a server-rounded
 *  total by a fraction of a penny. The drill table, the chart tooltip and
 *  Income by Source's Other band each wrote this with their own tolerance
 *  (0.005, 0.005 and 0.01), so a $0.007 gap was rounding on one and a
 *  truncated set on the others. */
export function isPartial(shown: number, whole: number): boolean {
  return Math.abs(whole - shown) >= CENT
}

/** `part` as a percentage of `whole`, 0–100 — or null when there is no
 *  positive whole to be a share of.
 *
 *  One policy for every share-of-total on the reports. There were six copies:
 *  five read a zero or negative whole as 0% and one (this table's footer)
 *  stated a share of a negative total, so on a window whose refunds beat its
 *  spending the footer quoted a percentage while the Pareto rows beside it
 *  read 0.0%. Neither is a fact: a share of nothing, or of a net refund, is
 *  unknown. A caller that must draw something anyway — a bar width, a
 *  point on a line — says so where it substitutes. */
export function shareOfTotal(part: number, whole: number): number | null {
  return whole > 0 ? (part / whole) * 100 : null
}

export function drillDownFooter(
  rows: readonly { amount: number }[],
  wider: WiderSet | undefined,
  formatMoney: (amount: number) => string
): DrillDownFooter {
  const shown = rows.reduce((sum, r) => sum + r.amount, 0)
  if (wider === undefined || !isPartial(shown, wider.total)) {
    return { shown, totalLabel: 'Total', wider: null, widerLabel: null, share: null }
  }
  const across =
    wider.count !== undefined && wider.label ? ` across ${wider.count} ${wider.label}` : ''
  return {
    shown,
    totalLabel: `Total of the ${rows.length} shown`,
    wider: wider.total,
    widerLabel: `of ${formatMoney(wider.total)}${across}`,
    share: shareOfTotal(shown, wider.total),
  }
}
