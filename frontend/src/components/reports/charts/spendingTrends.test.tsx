import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { monthWiderByLabel, rollupTrends } from './spendingTrends'
import { ChartTooltip } from './ChartTooltip'
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

describe('the whole month behind the stacked tooltip', () => {
  // Eleven series: the chart stacks ten, so the tooltip's sum is a subtotal.
  const eleven = {
    months: ['2026-08-01', '2026-09-01'],
    monthly_totals: [1100, 1210],
  }
  const label = (m: string) => `M${m.slice(5, 7)}`

  it('is the month total across every series, found by the axis label', () => {
    expect(monthWiderByLabel(eleven, label)('M09')).toEqual({ total: 1210, label: 'categories' })
  })

  it('is absent, not $0.00, for a label it does not know', () => {
    expect(monthWiderByLabel(eleven, label)('M10')).toBeUndefined()
  })

  it('draws the whole month beside the ten drawn series', () => {
    const drawn = Array.from({ length: 10 }, (_, i) => ({ name: `Cat ${i}`, value: 100 }))
    render(
      <ChartTooltip
        active
        showTotal
        payload={drawn}
        label="M08"
        wider={monthWiderByLabel(eleven, label)('M08')}
        formatter={(v) => `$${v}`}
      />
    )
    expect(screen.getByText('Total of the 10 shown')).toBeInTheDocument()
    expect(screen.getByText('All categories')).toBeInTheDocument()
    expect(screen.getByText('$1100')).toBeInTheDocument()
  })
})
