import { describe, expect, it } from 'vitest'
import { groupByMonthNewestFirst, percentChange, testedLine } from './anomaliesView'
import type { AnomalyItem } from '../../../types'

function anomaly(month: string, name: string, z: number): AnomalyItem {
  return {
    category_id: name,
    category_name: name,
    group_name: 'Everyday',
    month,
    actual: 300,
    baseline_mean: 100,
    usual_low: 80,
    usual_high: 120,
    z_score: z,
    direction: 'high',
    partial_month: false,
    history: [],
  }
}

describe('groupByMonthNewestFirst', () => {
  it('puts the newest month first, whatever the worst row was', () => {
    // Served worst first: a three-month-old 9σ spike used to head the page
    // above this month's 3σ one, and the months read out of order.
    const groups = groupByMonthNewestFirst([
      anomaly('2026-06-01', 'Gifts', 9),
      anomaly('2026-09-01', 'Dining', 3),
      anomaly('2026-06-01', 'Fuel', 4),
      anomaly('2026-08-01', 'Home', 2.5),
    ])
    expect(groups.map((g) => g.month)).toEqual(['2026-09-01', '2026-08-01', '2026-06-01'])
    // Within a month, the served order (worst first) stands.
    expect(groups[2].items.map((a) => a.category_name)).toEqual(['Gifts', 'Fuel'])
  })

  it('is empty for no anomalies', () => {
    expect(groupByMonthNewestFirst([])).toEqual([])
  })
})

describe('percentChange', () => {
  it('signs the change against the baseline', () => {
    expect(percentChange(300, 100)).toBe('+200%')
    expect(percentChange(40, 200)).toBe('-80%')
    expect(percentChange(100, 100)).toBe('+0%')
  })

  it('says infinity rather than dividing by a zero baseline', () => {
    expect(percentChange(50, 0)).toBe('+∞%')
    expect(percentChange(0, 0)).toBe('0%')
  })
})

describe('testedLine', () => {
  it('says how many categories were tested', () => {
    // "No unusual spending" over a budget too young to score read as a clean
    // bill of health it never gave.
    expect(
      testedLine({ categories_seen: 22, categories_tested: 14, sinking_funds_skipped: 0 })
    ).toBe('14 of 22 categories had six earlier months to test against.')
  })

  it('names the sinking funds it left out', () => {
    expect(testedLine({ categories_seen: 1, categories_tested: 1, sinking_funds_skipped: 2 })).toBe(
      '1 of 1 category had six earlier months to test against. 2 sinking funds are not tested: paying the bill a sinking fund saved for is the plan working.'
    )
  })

  it('says there was nothing to test', () => {
    expect(testedLine({ categories_seen: 0, categories_tested: 0, sinking_funds_skipped: 0 })).toBe(
      'No spending to test yet.'
    )
  })
})
