/** Pure math for the volatility report: error-bar spans and the coefficient
 * of variation. Extracted from VolatilityChart so it is unit-testable. */

import { truncateLabel } from '../../../utils/truncateLabel'

interface VolatilityCategoryLike {
  category_id: string
  category_name: string
  category_group_name: string
  mean: string | number
  std_dev: string | number
  min_val: string | number
  max_val: string | number
  months_included: number
}

export interface VolatilityChartRow {
  name: string
  Mean: number
  /** [below, above]: distance from mean down to min and up to max */
  errorY: [number, number]
  /** One-sided spans of the same range, so the two halves can be drawn in
   *  different colours: the low whisker lands ON the bar fill and the high
   *  whisker on the plot background — one stroke cannot read on both. */
  errorLow: [number, number]
  errorHigh: [number, number]
  StdDev: number
  Min: number
  Max: number
}

/** Categories with enough history to say anything about variation. */
export function filterVolatile<T extends VolatilityCategoryLike>(categories: T[]): T[] {
  return categories.filter((c) => c.months_included >= 2)
}

export function buildVolatilityChartRows(
  categories: VolatilityCategoryLike[],
  topN = 20
): VolatilityChartRow[] {
  return categories.slice(0, topN).map((c) => {
    const below = Number(c.mean) - Number(c.min_val)
    const above = Number(c.max_val) - Number(c.mean)
    return {
      name: truncateLabel(c.category_name, 16),
      Mean: Number(c.mean),
      errorY: [below, above] as [number, number],
      errorLow: [below, 0] as [number, number],
      errorHigh: [0, above] as [number, number],
      StdDev: Number(c.std_dev),
      Min: Number(c.min_val),
      Max: Number(c.max_val),
    }
  })
}

/** Coefficient of variation as a percentage: σ/mean × 100; 0 for mean ≤ 0. */
export function coefficientOfVariation(mean: number, stdDev: number): number {
  return mean > 0 ? (stdDev / mean) * 100 : 0
}

/**
 * What an export of the report is named and carries.
 *
 * The raw and amortized readings of one window differ in σ, min and max, so a
 * file has to say which one it holds: both used to be `igab-volatility.*` with
 * the same columns, which is the same numbers under two definitions with
 * nothing to tell them apart. `amortized` is the served flag, not the toggle —
 * it names what the figures ARE.
 */
export function volatilityExport(
  categories: VolatilityCategoryLike[],
  amortized: boolean
): { reportId: string; rows: Record<string, unknown>[] } {
  return {
    reportId: amortized ? 'volatility-amortized' : 'volatility',
    rows: categories.map((c) => ({
      category: c.category_name,
      group: c.category_group_name,
      reading: amortized ? 'amortized' : 'raw',
      mean: c.mean,
      std_dev: c.std_dev,
      min: c.min_val,
      max: c.max_val,
      months: c.months_included,
    })),
  }
}
