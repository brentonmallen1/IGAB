import { describe, expect, it } from 'vitest'
import { chartSeries, rolledUpCount, MAX_CHART_SERIES, OTHER_SERIES } from './costOfLivingChart'

const groups = (n: number, per = 10) =>
  Array.from({ length: n }, (_, i) => ({
    group_name: `G${i}`,
    monthly_amounts: [per, per],
  }))

describe('chartSeries', () => {
  it('draws every group when they fit', () => {
    const out = chartSeries(groups(3))
    expect(out.map((g) => g.group_name)).toEqual(['G0', 'G1', 'G2'])
  })

  it('draws exactly the cap without inventing an Other', () => {
    const out = chartSeries(groups(MAX_CHART_SERIES))
    expect(out).toHaveLength(MAX_CHART_SERIES)
    expect(out.some((g) => g.group_name === OTHER_SERIES)).toBe(false)
  })

  it('rolls the tail into one series past the cap', () => {
    const out = chartSeries(groups(12))
    expect(out).toHaveLength(MAX_CHART_SERIES)
    expect(out[out.length - 1].group_name).toBe(OTHER_SERIES)
  })

  it('keeps the money — the stack still totals what the table does', () => {
    // The bug this replaces: `slice(0, 8)` dropped groups 9+ from the chart
    // while the table listed them, so one screen said two different things
    // about what a month cost.
    const all = groups(12, 10)
    const drawn = chartSeries(all)
    const monthTotal = (list: { monthly_amounts: number[] }[], i: number) =>
      list.reduce((sum, g) => sum + g.monthly_amounts[i], 0)
    expect(monthTotal(drawn, 0)).toBe(monthTotal(all, 0))
    expect(monthTotal(drawn, 1)).toBe(monthTotal(all, 1))
  })

  it('sums the tail per month rather than across them', () => {
    const uneven = [
      ...groups(MAX_CHART_SERIES - 1, 100),
      { group_name: 'Tail1', monthly_amounts: [5, 1] },
      { group_name: 'Tail2', monthly_amounts: [3, 2] },
    ]
    const other = chartSeries(uneven).at(-1)!
    expect(other.group_name).toBe(OTHER_SERIES)
    expect(other.monthly_amounts).toEqual([8, 3])
  })

  it('handles a short month array without producing NaN', () => {
    const ragged = [
      ...groups(MAX_CHART_SERIES - 1, 100),
      { group_name: 'Tail1', monthly_amounts: [] },
      { group_name: 'Tail2', monthly_amounts: [4, 4] },
    ]
    const other = chartSeries(ragged).at(-1)!
    expect(other.monthly_amounts).toEqual([4, 4])
  })
})

describe('rolledUpCount', () => {
  it('is zero while everything is drawn', () => {
    expect(rolledUpCount(groups(MAX_CHART_SERIES))).toBe(0)
  })

  it('counts what Other stands for', () => {
    // 12 groups, 7 named, so Other is 5 of them.
    expect(rolledUpCount(groups(12))).toBe(5)
  })
})
