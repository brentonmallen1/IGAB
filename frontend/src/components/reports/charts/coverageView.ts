/**
 * How the coverage report reads its own series.
 *
 * Pure, so the sentence the page puts under the headline is a one-line test
 * rather than something you have to mount a chart to check.
 */
import type { CoveragePoint } from '../../../types'

/** Coverage at the start of the window and at its end, when both are known. */
export interface CoverageTrend {
  from: number
  to: number
  /** Positive means the fund now covers more months than it did. */
  delta: number
  /** How many months the reading actually spans.
   *
   * Points with no coverage figure are dropped — a month with no essential
   * spending has no answer — so the span is not the window the user picked.
   * The card labelled the delta "over {months} months" regardless, which
   * overstated the period on any budget with a gap in it. */
  months: number
}

export function coverageTrend(series: readonly CoveragePoint[]): CoverageTrend | null {
  const known = series.filter((p) => p.coverage_months !== null)
  // One point is a reading, not a trend — "up from itself" is not a sentence.
  if (known.length < 2) return null
  const from = known[0].coverage_months as number
  const to = known[known.length - 1].coverage_months as number
  return { from, to, delta: Number((to - from).toFixed(1)), months: known.length }
}

/**
 * Where the fund stands against the roadmap's band.
 *
 * `short` is the gap to the LOW end, because that is the number someone can
 * act on — the high end is where you stop, not where you start.
 */
export type CoverageStanding = 'none' | 'below' | 'within' | 'above'

export function standing(
  coverage: number | null,
  [low, high]: readonly [number, number]
): CoverageStanding {
  if (coverage === null) return 'none'
  if (coverage < low) return 'below'
  return coverage <= high ? 'within' : 'above'
}

/**
 * Months of contributions to reach the low end, at the pace of the window.
 *
 * Null when the fund is not growing — an "in ∞ months" is worse than saying
 * nothing, and a shrinking fund has no date at all. Null too when the target
 * is already met, which the standing says better.
 */
export function monthsToTarget(series: readonly CoveragePoint[]): number | null {
  if (series.length < 2) return null
  const first = series[0]
  const last = series[series.length - 1]
  const gap = last.target_low - last.fund_balance
  if (gap <= 0) return null
  // The pace of the whole window, not the last step: one big month is a
  // windfall, and dividing a gap by a windfall promises a date nobody can keep.
  const pace = (last.fund_balance - first.fund_balance) / (series.length - 1)
  if (pace <= 0) return null
  return Math.ceil(gap / pace)
}
