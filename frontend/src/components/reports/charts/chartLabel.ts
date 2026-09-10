/**
 * Truncating a chart label, once.
 *
 * This was written five times with five different thresholds — 14, 16, 18, 20
 * and 24 — so one category name rendered differently depending on which report
 * you were looking at, and "Harborstone Utilities" was three different strings
 * across Volatility, Budget vs Actual and Seasonality.
 *
 * The threshold is genuinely per-chart: a Pareto bar label has less room than a
 * heatmap row heading. So `max` stays a parameter and the RULE lives here —
 * that is the difference between a deliberate variation and five copies.
 */

/** The label, cut to `max` characters with an ellipsis if it does not fit.
 *
 * Two characters come off before the ellipsis is added, so the result is never
 * wider than `max`. A cut can therefore land on a space and leave "Cascade
 * Point …". That is what all five copies did, and it is preserved rather than
 * tidied: trimming would move labels on six reports at once, which is a
 * decision for a design pass, not a consolidation.
 */
export function truncateLabel(label: string, max: number): string {
  return label.length > max ? label.slice(0, max - 2) + '…' : label
}
