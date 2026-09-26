import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { OTHER_KEY, rollupTrends, stackTrends, type TrendRow } from './spendingTrends'
import { ChartTooltip } from './ChartTooltip'
import { COLOR_OTHER, chartColor } from './chartColors'
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
  monthly_average: 1500,
  months_averaged: 1,
  latest_complete: false,
  class_excluded: [],
  filter_unavailable: false,
  counted_classes: ['spending'],
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

/** Twelve categories of 100 a month: ten drawn by name, two in the tail. */
function twelve() {
  const rolled: TrendRow[] = Array.from({ length: 12 }, (_, i) => ({
    key: `c${i}`,
    name: `Cat ${i}`,
    group_name: null,
    monthly: [100, 100],
    total: 200,
  }))
  const months = { months: ['2026-08-01', '2026-09-01'], monthly_totals: [1200, 1200] }
  return { rolled, months }
}
const label = (m: string) => `M${m.slice(5, 7)}`
const barTotal = (row: Record<string, string | number>) =>
  Object.entries(row)
    .filter(([k]) => k !== 'month')
    .reduce((sum, [, v]) => sum + Number(v), 0)

describe('the stacked Spending Trends chart', () => {
  it('stacks the ten largest and one Other band, so each bar is its month', () => {
    // The chart stacked the ten largest and nothing else: this month's bar
    // stood at 1,000 under an axis, cards and All row reading 1,200.
    const { rolled, months } = twelve()
    const { rows, series } = stackTrends(months, rolled, label)
    expect(series.map((s) => s.name)).toEqual([...rolled.slice(0, 10).map((r) => r.name), 'Other'])
    expect(rows.map((r) => r[OTHER_KEY])).toEqual([200, 200])
    expect(rows.map(barTotal)).toEqual([1200, 1200])
  })

  it('draws no Other when the named series are the whole of every month', () => {
    const { rows, series } = stackTrends(data, rollupTrends(data, 'category'), label)
    expect(series.map((s) => s.key)).toEqual(['g', 'f', 'r'])
    expect(rows[0]).not.toHaveProperty(OTHER_KEY)
    expect(rows.map(barTotal)).toEqual([1500, 1590])
  })

  it('carries a negative Other for a tail that refunded more than it spent', () => {
    // The tail's two categories each net a 25 refund in August: 1,000 drawn,
    // 950 whole. Dropping the band would stand the bar at 1,000.
    const { rolled, months } = twelve()
    const refunded = stackTrends(
      { ...months, monthly_totals: [950, 1200] },
      rolled.map((r, i) => (i >= 10 ? { ...r, monthly: [-25, 100] } : r)),
      label
    )
    expect(refunded.rows[0][OTHER_KEY]).toBe(-50)
    expect(refunded.rows.map(barTotal)).toEqual([950, 1200])
  })

  it('leaves Other out of a month the named series already cover', () => {
    const { rolled, months } = twelve()
    const { rows, series } = stackTrends(
      { ...months, monthly_totals: [1000, 1200] },
      rolled.map((r, i) => (i >= 10 ? { ...r, monthly: [0, 100] } : r)),
      label
    )
    expect(rows[0]).not.toHaveProperty(OTHER_KEY)
    expect(rows[1][OTHER_KEY]).toBe(200)
    expect(series.at(-1)).toMatchObject({ key: OTHER_KEY, total: 200 })
  })

  it('keys each series by id, so a category named "Other" is not the band', () => {
    const rolled: TrendRow[] = [
      { key: 'c1', name: 'Other', group_name: null, monthly: [50], total: 50 },
    ]
    const { rows, series } = stackTrends(
      { months: ['2026-08-01'], monthly_totals: [80] },
      rolled,
      label,
      1
    )
    expect(rows[0]).toMatchObject({ c1: 50, [OTHER_KEY]: 30 })
    expect(series.map((s) => s.key)).toEqual(['c1', OTHER_KEY])
  })

  it('colours the named series by slot and Other in its own neutral', () => {
    const { rolled, months } = twelve()
    const { series } = stackTrends(months, rolled, label)
    expect(series[8].color).toBe(chartColor(8))
    expect(series.at(-1)?.color).toBe(COLOR_OTHER)
  })

  it('has nothing to draw for an empty window', () => {
    expect(stackTrends({ months: [], monthly_totals: [] }, [], label)).toEqual({
      rows: [],
      series: [],
    })
  })

  it('totals the tooltip to the month, with no separate "All" line', () => {
    const { rolled, months } = twelve()
    const { rows, series } = stackTrends(months, rolled, label)
    const payload = series.map((s) => ({ name: s.name, value: Number(rows[0][s.key] ?? 0) }))
    render(
      <ChartTooltip active showTotal payload={payload} label="M08" formatter={(v) => `$${v}`} />
    )
    expect(screen.getByText('Total')).toBeInTheDocument()
    expect(screen.getByText('$1200')).toBeInTheDocument()
    expect(screen.queryByText(/^All/)).toBeNull()
  })
})

describe('the Uncategorized series', () => {
  it('is keyed apart from every category, and rolls up under its own group', () => {
    // Trends used to leave uncategorized spending out; it is served with no
    // id and no group id now.
    const withLine: SpendingTrendsReport = {
      ...data,
      series: [
        ...data.series,
        {
          id: null,
          name: 'Uncategorized',
          group_id: null,
          group_name: 'Uncategorized',
          monthly: [20, 0],
          total: 20,
        },
      ],
    }
    expect(rollupTrends(withLine, 'category').at(-1)?.key).toBe('__uncategorized__')
    expect(rollupTrends(withLine, 'group').map((r) => r.name)).toContain('Uncategorized')
  })
})
