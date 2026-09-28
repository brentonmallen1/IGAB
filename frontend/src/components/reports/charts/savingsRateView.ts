/** The Savings Rate chart's formatters, pure so they are testable: the chart
 * renders at zero size under jsdom, so its tooltip never reaches the DOM. */

/** The rate line's dataKey. What the legend and tooltip call it is
 *  `savingsRateLabel`. */
export const RATE_SERIES = 'Savings Rate'

/** A served rate — a fraction, 0.185 — as a percentage number, 18.5. The
 * chart's 0–100 axis and the Overview's export both read it. */
export function ratePercent(v: number): number {
  return v * 100
}

/** A savings rate — a fraction, 0.185 — as "18.5%"; "—" for a window with no
 * income, which has no rate.
 *
 * Every savings-rate card reads this: the tab's summary, the Overview's card
 * and the dialog either one opens. The Overview used to clamp a negative rate
 * to 0% with its own formatter while the tab printed it, so a month that drew
 * more out of savings than it put in read 0.0% on one card and −3.0% on the
 * other — and a dialog listing a negative "Saved" beside 0% would contradict
 * itself. A negative rate is a fact: money came back out of savings. */
export function pct(v: number | null): string {
  return v === null ? '—' : `${ratePercent(v).toFixed(1)}%`
}

/** The rate panel's tooltip formatter. The line plots the rate ×100 for its
 * percentage axis, so it is divided back and said by `pct`, as the card says
 * it. The shared money default used to render the rate 18.5 as "$18.50", and
 * the first fix wrote the rate with its own `toFixed(1)` beside the card's
 * `pct` — two formatters for one figure. The rate has its own panel now (the
 * money bars have theirs), so the tooltip no longer branches on a series
 * name. */
export function rateTooltip(value: number): string {
  return pct(value / 100)
}

/** What a savings rate divides income into: Saved, and — when the rate
 *  counts them — debt payments. The Saved card and the stacked bar both read
 *  this, so the figure the card states is the bar the chart draws.
 *
 *  The card said "Saved" and showed Saved alone while the rate beside it
 *  counted debt payments too, so the card's two figures did not divide into
 *  the rate it sat next to. */
export function keptFigure(
  row: { savings: number; debt_principal: number },
  withDebt: boolean
): number {
  return withDebt ? row.savings + row.debt_principal : row.savings
}
