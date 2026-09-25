/**
 * The burn rate's comparison, as the Overview card and the Burn Rate tab say it.
 *
 * Both figures are served (`domain/burn_rate.py`): net spending over the last
 * 30 days, and over the 60 days before them per 30 days. They share no day, so
 * the change between them is the change a reader means by "am I spending more
 * than I was". The old second figure was a 90-day average that contained the
 * 30 days it was compared with, so a spike moved both and the card read two
 * nearly equal numbers exactly when they should have parted.
 *
 * The percentage is presentational composition of those two served numbers,
 * so it lives here, once, for both surfaces. Whether there is a percentage at
 * all is `spendingDelta`'s rule — the one the Spent card reads — so "no prior
 * spending, no percentage" is decided in one place.
 */
import { spendingDelta } from '../overviewMetrics'

/** A change as the burn lines print it: whole percent, signed. A change that
 *  rounds to nothing is "0%", never "−0%". */
export function signedWholePercent(pct: number): string {
  const rounded = Math.round(pct)
  if (rounded === 0) return '0%'
  return rounded > 0 ? `+${rounded}%` : `−${-rounded}%`
}

/** The last 30 days against the prior 60's pace, "+8%"; null when the prior
 *  60 days had no spending to compare with. */
export function burnChange(recent: number, prior: number): string | null {
  const change = spendingDelta(recent, prior)
  return change === null ? null : signedWholePercent(change)
}

/** The Overview card's sub-line: "Prior 60 days: $600.00/30d · +8%". */
export function burnPriorLine(
  recent: number,
  prior: number,
  formatMoney: (n: number) => string
): string {
  const base = `Prior 60 days: ${formatMoney(prior)}/30d`
  const change = burnChange(recent, prior)
  return change === null ? base : `${base} · ${change}`
}

/** The Burn Rate tab's 30-day card, which sits beside a card showing the
 *  prior figure itself: "+8% on the prior 60 days". */
export function burnChangeLine(recent: number, prior: number): string {
  const change = burnChange(recent, prior)
  return change === null ? 'No spending in the prior 60 days' : `${change} on the prior 60 days`
}

/** The chart's second series: the prior 60 days, per 30 — the legend's name
 *  and the dataKey both. */
export const PRIOR_SERIES = 'Prior 60 days, per 30'
