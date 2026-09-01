import { describe, expect, it } from 'vitest'
import { buildVolatilityChartRows, coefficientOfVariation, filterVolatile } from './volatilityData'

const cat = (over: Partial<Parameters<typeof buildVolatilityChartRows>[0][number]> = {}) => ({
  category_id: 'c1',
  category_name: 'Groceries',
  category_group_name: 'Everyday',
  mean: '100',
  std_dev: '20',
  min_val: '60',
  max_val: '150',
  months_included: 6,
  ...over,
})

describe('filterVolatile', () => {
  it('drops categories with fewer than 2 months of history', () => {
    const kept = filterVolatile([cat(), cat({ category_id: 'c2', months_included: 1 })])
    expect(kept.map((c) => c.category_id)).toEqual(['c1'])
  })
})

describe('buildVolatilityChartRows', () => {
  it('spans the error bar from mean down to min and up to max', () => {
    const [row] = buildVolatilityChartRows([cat()])
    expect(row.Mean).toBe(100)
    expect(row.errorY).toEqual([40, 50]) // 100-60 below, 150-100 above
    expect(row.Min).toBe(60)
    expect(row.Max).toBe(150)
  })

  it('splits the range into one-sided spans, one per background', () => {
    // The low whisker is drawn on the bar fill, the high one on the plot —
    // two colours, so two spans that together are exactly errorY.
    const [row] = buildVolatilityChartRows([cat()])
    expect(row.errorLow).toEqual([40, 0])
    expect(row.errorHigh).toEqual([0, 50])
  })

  it('caps the chart at topN rows', () => {
    const many = Array.from({ length: 25 }, (_, i) => cat({ category_id: `c${i}` }))
    expect(buildVolatilityChartRows(many)).toHaveLength(20)
  })
})

describe('coefficientOfVariation', () => {
  it('is sigma over mean as a percentage', () => {
    expect(coefficientOfVariation(100, 20)).toBe(20)
  })

  it('is 0 for a non-positive mean instead of dividing by zero', () => {
    expect(coefficientOfVariation(0, 20)).toBe(0)
  })
})
