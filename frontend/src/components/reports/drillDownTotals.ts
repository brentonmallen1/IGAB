/** The footer under a drill-down table: what the rows add up to, and what
 * they were taken from.
 *
 * `DrillDownTable`'s `total` prop was a free-form number with no relation to
 * `rows`, and two of its callers handed it a WIDER set: Budget vs Actual
 * passed the period's whole spend while "Overspent only" was ticked, and
 * Payee Analysis passed every payee's total beside its top-20 slice. So the
 * row headed Total was larger than the column above it — the one number on
 * the table a reader can check on paper.
 *
 * The rule, in one place: **the total is the sum of the rows it sits under.**
 * A wider set is context beside it, never the rows' own figure.
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
  /** The wider set's total, or null when the rows ARE the whole set. */
  wider: number | null
  /** What to call the wider figure: "of $9,850 across 312 payees". */
  widerLabel: string | null
  /** The shown rows' share of the wider total, 0–100, or null. */
  share: number | null
}

/** Money differences below this are rounding, not a truncated set. */
const CENT = 0.005

export function drillDownFooter(
  rows: readonly { amount: number }[],
  wider: WiderSet | undefined,
  formatMoney: (amount: number) => string
): DrillDownFooter {
  const shown = rows.reduce((sum, r) => sum + r.amount, 0)
  if (wider === undefined || Math.abs(wider.total - shown) < CENT) {
    return { shown, wider: null, widerLabel: null, share: null }
  }
  const across =
    wider.count !== undefined && wider.label ? ` across ${wider.count} ${wider.label}` : ''
  return {
    shown,
    wider: wider.total,
    widerLabel: `of ${formatMoney(wider.total)}${across}`,
    share: wider.total !== 0 ? (shown / wider.total) * 100 : null,
  }
}
