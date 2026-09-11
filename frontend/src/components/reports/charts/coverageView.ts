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
  /** How many months the reading actually spans: first known point to last,
   * inclusive.
   *
   * Points with no coverage figure — a month with no essential spending has
   * no answer — are not endpoints, so a gap at either edge shortens the span
   * and the card must not label it with the window the user picked. A gap
   * BETWEEN the endpoints does not: January to April is four months whether
   * or not February had an answer, and counting only the known points said
   * two. */
  months: number
}

export function coverageTrend(series: readonly CoveragePoint[]): CoverageTrend | null {
  const first = series.findIndex((p) => p.coverage_months !== null)
  const last = series.findLastIndex((p) => p.coverage_months !== null)
  // One point is a reading, not a trend — "up from itself" is not a sentence.
  if (first === -1 || first === last) return null
  const from = series[first].coverage_months as number
  const to = series[last].coverage_months as number
  return { from, to, delta: Number((to - from).toFixed(1)), months: last - first + 1 }
}

/**
 * The month the self-reported part of the fund is counted from — the first
 * point the server marked `external_counted` — or null when none is.
 *
 * Not the served `external_as_of`: that is the raw stamp, which for a figure
 * saved today names the running month, while the server counts it from the
 * newest COMPLETE month. The note then named a month the chart does not draw,
 * one after the only point that counts the fund.
 */
export function carriedFlatFrom(series: readonly CoveragePoint[]): string | null {
  return series.find((p) => p.external_counted)?.month ?? null
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
