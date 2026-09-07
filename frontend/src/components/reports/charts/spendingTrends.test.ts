import { describe, expect, it } from 'vitest'
import { rollupTrends } from './spendingTrends'
import type { SpendingTrendsReport } from '../../../types'

const data: SpendingTrendsReport = {
  months: ['2026-08-01', '2026-09-01'],
  series: [
    {
      id: 'g',
      name: 'Groceries',
      group_id: 'e',
      group_name: 'Everyday',
      monthly: [100, 150],
      total: 250,
    },
    { id: 'f', name: 'Fun', group_id: 'e', group_name: 'Everyday', monthly: [0, 40], total: 40 },
    {
      id: 'r',
      name: 'Rent',
      group_id: 'b',
      group_name: 'Bills',
      monthly: [1400, 1400],
      total: 2800,
    },
  ],
  monthly_totals: [1500, 1590],
  total: 3090,
  class_excluded: [],
  filter_unavailable: false,
}

describe('rollupTrends', () => {
  it('by category keeps every series as served', () => {
    expect(rollupTrends(data, 'category').map((r) => r.name)).toEqual(['Groceries', 'Fun', 'Rent'])
  })

  it('by group sums the months and orders the largest first', () => {
    const rows = rollupTrends(data, 'group')
    expect(rows.map((r) => [r.name, r.monthly, r.total])).toEqual([
      ['Bills', [1400, 1400], 2800],
      ['Everyday', [100, 190], 290],
    ])
  })
})
