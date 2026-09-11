/**
 * The values each report control can send the server, in one place.
 *
 * `shared/report_controls.json` holds the same lists: reportControls.test.ts
 * holds these to it, and the backend sends every one and requires a 200. The
 * server's bounds were tested only at their defaults, so tightening one to
 * the default would have 422'd the rest of a control's options with every
 * test green.
 */

/** Cash Projection's horizon, in days. */
export const HORIZON_OPTIONS = [30, 60, 90, 180] as const

/** Days after a payday the Day-of-Week chart's payday panel follows. */
export const PAYDAY_WINDOW_OPTIONS = [7, 14, 21] as const

/** How many rows the Large Transactions timeline asks for. */
export const TIMELINE_LIMITS = [25, 50, 100] as const

/** The Anomalies z-score threshold, strictest first. */
export const SENSITIVITY_OPTIONS = [
  { value: 3.0, label: 'Strict', description: 'z ≥ 3' },
  { value: 2.5, label: 'Normal', description: 'z ≥ 2.5' },
  { value: 2.0, label: 'Sensitive', description: 'z ≥ 2' },
] as const

/** How many payees the server ranks for Payee Analysis and Pareto. One number
 *  so the two charts share one query rather than ranking twice. */
export const PAYEE_RANKED = 25
