/**
 * What Income by Source's chart does with a month that is not all positive.
 *
 * A payee's month can be negative — a reconciliation adjustment filed to
 * Ready to Assign is income by class — and recharts' default stack offset
 * ("none") draws that segment downwards from the top of the one below it, so
 * it paints over its neighbour and leaves the bar standing at the month's
 * gross. The arithmetic lives in `incomeSourcesView`; what this pins is the
 * wiring around it, which no pure test can see: the offset the chart is given,
 * that a negative Other band reaches the chart as a band, and that the
 * tooltip's Total is the month's net.
 *
 * recharts renders zero-size under jsdom, so it is stubbed: each stub records
 * the props the report handed it.
 */
import { render, screen, within } from '@testing-library/react'
import type { ReactElement, ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

type Row = Record<string, string | number>
type TooltipContent = (p: {
  active: boolean
  payload: { name: string; value: number }[]
  label: string
}) => ReactElement | null

const chart = vi.hoisted(() => ({
  stackOffset: undefined as string | undefined,
  data: [] as Row[],
  bars: [] as string[],
  tooltipContent: null as TooltipContent | null,
}))

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  BarChart: ({
    data,
    stackOffset,
    children,
  }: {
    data: Row[]
    stackOffset?: string
    children: ReactNode
  }) => {
    chart.data = data
    chart.stackOffset = stackOffset
    return <div data-testid="bar-chart">{children}</div>
  },
  Bar: ({ dataKey }: { dataKey: string }) => {
    if (!chart.bars.includes(dataKey)) chart.bars.push(dataKey)
    return null
  },
  Tooltip: ({ content }: { content: TooltipContent }) => {
    chart.tooltipContent = content
    return null
  },
  CartesianGrid: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Legend: () => null,
}))

const queryState = vi.hoisted(() => ({ current: { data: undefined as unknown } }))

vi.mock('../../../api/reports', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  const mocked: Record<string, unknown> = {}
  for (const key of Object.keys(actual)) {
    mocked[key] = key.startsWith('use')
      ? () => ({ ...queryState.current, isLoading: false, isError: false, refetch: () => {} })
      : actual[key]
  }
  return mocked
})

import { IncomeSourcesReport } from './IncomeSourcesReport'

/** Eight payees paying 375 each, plus one that only took money back. The
 *  server sorts by total, so the negative one falls outside the eight series
 *  the chart draws and lands in the Other band. */
const SHOWN = [
  'Northwind Payserv',
  'Cascade Point HYSA',
  'Willow Creek Rentals',
  'Ridgeline Co-op',
  'Beacon Hill Trust',
  'Foxglove Studio',
  'Tidewater Freelance',
  'Alder Lane Tutoring',
]

const DATA = {
  months: ['2026-09-01'],
  sources: [
    ...SHOWN.map((payee_name, i) => ({
      payee_id: `p${i}`,
      payee_name,
      monthly: [375],
      total: 375,
      count: 1,
    })),
    { payee_id: 'p9', payee_name: 'Harborstone', monthly: [-75], total: -75, count: 1 },
  ],
  monthly_totals: [2925],
  total: 2925,
  avg_monthly: 2925,
  months_averaged: 1,
}

beforeEach(() => {
  chart.stackOffset = undefined
  chart.data = []
  chart.bars = []
  chart.tooltipContent = null
  queryState.current = { data: DATA }
})

describe('Income by Source with a negative month', () => {
  it('stacks by sign, so a negative segment hangs below the axis', () => {
    render(<IncomeSourcesReport budgetId="b1" />)
    // "none" — recharts' default — stacks the -75 down from 3,000 and paints
    // it over the series below, leaving a bar that reads 3,000 for a 2,925
    // month.
    expect(chart.stackOffset).toBe('sign')
  })

  it('draws the negative remainder as an Other band', () => {
    render(<IncomeSourcesReport budgetId="b1" />)
    expect(chart.bars).toContain('Other')
    expect(chart.data[0].Other).toBe(-75)
  })

  it('counts only the payees that paid something as Sources', () => {
    render(<IncomeSourcesReport budgetId="b1" />)
    const card = screen
      .getByText('Sources', { selector: '.metric-card__label' })
      .closest('.metric-card')
    // Nine payees, one of them a -75 adjustment.
    expect(card?.querySelector('.metric-card__value')?.textContent).toBe('8')
  })

  it('totals the tooltip to the month net, the figure the All row carries', () => {
    render(<IncomeSourcesReport budgetId="b1" />)
    const row = chart.data[0]
    // Scoped to the tooltip's own container: the cards and the table print
    // these figures too.
    const tip = render(
      <>
        {chart.tooltipContent?.({
          active: true,
          payload: chart.bars.map((name) => ({ name, value: Number(row[name]) })),
          label: 'Sep 2026',
        })}
      </>
    )
    const tooltip = within(tip.container)
    expect(tooltip.getByText('-$75.00')).toBeInTheDocument()
    expect(tooltip.getByText('$2,925.00')).toBeInTheDocument()
  })
})
