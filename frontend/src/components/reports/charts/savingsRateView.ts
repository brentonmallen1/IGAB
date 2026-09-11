/** The Savings Rate chart's formatters, pure so they are testable: the chart
 * renders at zero size under jsdom, so its tooltip never reaches the DOM. */

/** The rate line's series name, used as both the dataKey and the tooltip key. */
export const RATE_SERIES = 'Savings Rate'

/** A savings rate — a fraction, 0.185 — as "18.5%"; "—" for a month with no
 * income, which has no rate. The metric card and the tooltip both read it. */
export function pct(v: number | null): string {
  return v === null ? '—' : `${(v * 100).toFixed(1)}%`
}

/** The chart's one tooltip: the rate line is a percentage, the three bars
 * beside it are money, so it branches on the series name. The shared default
 * used to render the rate 18.5 as "$18.50", and the first fix wrote the rate
 * with its own `toFixed(1)` beside the card's `pct` — two formatters for one
 * figure. The line plots the rate ×100 for its 0–100 axis, so it is divided
 * back here. */
export function savingsRateTooltipWith(formatMoney: (n: number) => string) {
  return (value: number, name: string): string =>
    name === RATE_SERIES ? pct(value / 100) : formatMoney(value)
}
