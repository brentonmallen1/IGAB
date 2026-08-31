/** Pure math for the volatility report: error-bar spans and the coefficient
 * of variation. Extracted from VolatilityChart so it is unit-testable. */

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
  return categories.slice(0, topN).map((c) => ({
    name: c.category_name.length > 16 ? c.category_name.slice(0, 14) + '…' : c.category_name,
    Mean: Number(c.mean),
    errorY: [Number(c.mean) - Number(c.min_val), Number(c.max_val) - Number(c.mean)],
    StdDev: Number(c.std_dev),
    Min: Number(c.min_val),
    Max: Number(c.max_val),
  }))
}

/** Coefficient of variation as a percentage: σ/mean × 100; 0 for mean ≤ 0. */
export function coefficientOfVariation(mean: number, stdDev: number): number {
  return mean > 0 ? (stdDev / mean) * 100 : 0
}
