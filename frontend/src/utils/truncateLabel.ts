/**
 * Truncating a label, once.
 *
 * Eight copies, with five thresholds (14, 16, 18, 20, 24) and two cut rules.
 * Six charts kept `max - 2` characters before the ellipsis; the treemap's
 * tile label and the Activity page's names kept `max - 1`, so at the same
 * limit "Harborstone Utilities" read "Harborstone Ut…" on one and
 * "Harborstone Uti…" on the other. Two features use the rule, so it lives in
 * utils/.
 *
 * The threshold is genuinely per-caller: a Pareto bar label has less room than
 * a Sankey node. So `max` stays a parameter and the RULE lives here — that is
 * the difference between a deliberate variation and eight copies.
 */

/** The label, cut to `max` characters with an ellipsis if it does not fit.
 *
 * Two characters come off before the ellipsis is added, so the result is never
 * wider than `max`. That is the six-chart majority's rule, kept so the
 * consolidation moves only the two labels that differed. A cut can land on a
 * space and leave "Cascade Point …"; trimming it would move labels everywhere
 * at once, which is a decision for a design pass, not a consolidation.
 */
export function truncateLabel(label: string, max: number): string {
  return label.length > max ? label.slice(0, max - 2) + '…' : label
}
