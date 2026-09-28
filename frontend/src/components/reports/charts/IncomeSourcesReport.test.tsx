/**
 * What Income by Source's chart does with a month that is not all positive.
 *
 * A payee's month can be negative — a reconciliation adjustment filed to
 * Ready to Assign is income by class — and recharts' default stack offset
 * ("none") draws that segment downwards from the top of the one below it, so
 * it paints over its neighbour and leaves the bar standing at the month's
 * gross. The arithmetic lives in `drillDownTotals.otherBand`; what this pins is the
 * wiring around it, which no pure test can see: the offset the chart is given,
 * that a negative Other band reaches the chart as a band, and that the
 * tooltip's Total is the month's net.
 *
 * recharts renders zero-size under jsdom, so it is stubbed: each stub records
 * the props the report handed it.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
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
  yAxis: null as { domain?: [number, number]; ticks?: number[] } | null,
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
  YAxis: (props: { domain?: [number, number]; ticks?: number[] }) => {
    chart.yAxis = props
    return null
  },
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
import { OTHER_KEY } from './spendingTrends'

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
  chart.yAxis = null
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
    // Keyed by id like every stacked series, never by name: a payee called
    // "Other" is not the band.
    expect(chart.bars).toContain(OTHER_KEY)
    expect(chart.data[0][OTHER_KEY]).toBe(-75)
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

describe('Income by Source key and axis', () => {
  it('lists the key in the order the bars stack, Other last — not alphabetically', () => {
    render(<IncomeSourcesReport budgetId="b1" />)
    const names = within(screen.getByRole('list', { name: 'Series in this chart' }))
      .getAllByRole('button')
      .map((b) => b.querySelector('.chart-legend__name')?.textContent)
    // recharts' own legend sorted by name, so the key read Alder, Beacon,
    // Cascade… over a stack that ran Northwind, Cascade, Willow…
    expect(names).toEqual([...SHOWN, 'Other'])
    expect(chart.bars).toEqual([...SHOWN.map((_, i) => `p${i}`), OTHER_KEY])
  })

  it('keeps two payees who share a name apart', () => {
    queryState.current = {
      data: {
        ...DATA,
        sources: [
          { payee_id: 'a', payee_name: 'Payment', monthly: [2000], total: 2000, count: 1 },
          { payee_id: 'b', payee_name: 'Payment', monthly: [925], total: 925, count: 1 },
        ],
      },
    }
    render(<IncomeSourcesReport budgetId="b1" />)
    expect(chart.bars).toEqual(['a', 'b'])
    expect(chart.data[0]).toMatchObject({ a: 2000, b: 925 })
  })

  it('gives a small negative adjustment a sliver of axis, not a whole step', () => {
    render(<IncomeSourcesReport budgetId="b1" />)
    // Eight 375s stack to 3,000 over a -75 Other band.
    const [bottom, top] = chart.yAxis?.domain ?? [0, 0]
    expect(top).toBe(3000)
    expect(bottom).toBeLessThan(-75)
    expect(bottom).toBeGreaterThan(-750)
    expect(chart.yAxis?.ticks?.[0]).toBe(0)
  })

  it('states which accounts it reads in its ⓘ', () => {
    render(<IncomeSourcesReport budgetId="b1" />)
    fireEvent.click(screen.getByRole('button', { name: 'About the Income by Source report' }))
    expect(screen.getByText(/^Accounts:/)).toBeInTheDocument()
  })
})
