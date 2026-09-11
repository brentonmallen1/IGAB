/**
 * `ChartTooltip` used to default its formatter to a hard-coded
 * `$${v.toLocaleString('en-US', ...)}`, and eighteen of its nineteen call
 * sites passed nothing. Each inherited three defects: the budget's currency
 * and number format ignored, privacy mode defeated, and — on the two charts
 * whose series are not money — a percentage and a month count printed as
 * dollars. It also put the minus in the wrong place: `$-1,200.00` where every
 * other figure in the app reads `-$1,200.00`.
 *
 * The prop is required now, so these pin the contract that replaced the
 * default: the tooltip renders exactly what the formatter returns, and it
 * hands over the series name so a mixed-unit chart can branch.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ChartTooltip } from './ChartTooltip'

describe('ChartTooltip', () => {
  it('renders exactly what the formatter returns, adding no currency of its own', () => {
    render(
      <ChartTooltip
        active
        payload={[{ name: 'Net Worth', value: -1200 }]}
        formatter={(v) => `-€${Math.abs(v).toFixed(2)}`}
      />
    )
    // The old default would have drawn "$-1,200.00" here.
    expect(screen.getByText('-€1200.00')).toBeInTheDocument()
    expect(screen.queryByText(/\$/)).toBeNull()
  })

  it('can be masked, which is what privacy mode needs', () => {
    render(
      <ChartTooltip
        active
        payload={[{ name: 'Fund', value: 412880.5 }]}
        formatter={() => '$••••'}
      />
    )
    expect(screen.getByText('$••••')).toBeInTheDocument()
    expect(screen.queryByText(/412|880/)).toBeNull()
  })

  it('passes the series name, so one tooltip can serve two units', () => {
    // SavingsRateChart's real shape: money bars plus a percentage line. The
    // shared default rendered the rate 18.5 as "$18.50".
    const formatter = (value: number, name: string) =>
      name === 'Savings Rate' ? `${value.toFixed(1)}%` : `$${value.toFixed(2)}`
    render(
      <ChartTooltip
        active
        payload={[
          { name: 'Saved', value: 900 },
          { name: 'Savings Rate', value: 18.5 },
        ]}
        formatter={formatter}
      />
    )
    expect(screen.getByText('$900.00')).toBeInTheDocument()
    expect(screen.getByText('18.5%')).toBeInTheDocument()
  })

  it('formats the total row through the same formatter', () => {
    const formatter = vi.fn((v: number) => `$${v.toFixed(2)}`)
    render(
      <ChartTooltip
        active
        showTotal
        payload={[
          { name: 'Rent', value: 1400 },
          { name: 'Groceries', value: 600 },
        ]}
        formatter={formatter}
      />
    )
    expect(screen.getByText('$2000.00')).toBeInTheDocument()
    expect(formatter).toHaveBeenCalledWith(2000, 'Total')
  })

  it('draws nothing when inactive or empty', () => {
    const { container: a } = render(
      <ChartTooltip payload={[{ name: 'x', value: 1 }]} formatter={String} />
    )
    expect(a).toBeEmptyDOMElement()
    const { container: b } = render(<ChartTooltip active payload={[]} formatter={String} />)
    expect(b).toBeEmptyDOMElement()
  })
})

/* The "every call site passes a formatter" ratchet deliberately lives in
 * eslint (`NO_UNFORMATTED_CHART_TOOLTIP` in frontend/eslint.config.js), not
 * here. A first draft of it scanned the source with a regex and reported eight
 * false positives: `<ChartTooltip` spread over several lines defeats a
 * non-greedy match, because `payload={payload?.map((p) => ({` contains both a
 * `>` and a `}`, and this file's own docstring mentions the tag in prose.
 * eslint sees the JSX tree instead, so it gets the answer right — and a second,
 * worse implementation of a rule that already has a home is the thing this
 * whole change is removing. Required prop (tsc) + eslint rule are the guards.
 */

describe('a stacked tooltip whose chart draws only some of the series', () => {
  it('heads its own sum as the rows it lists and states the whole beside it', () => {
    // Spending Trends stacks the ten largest series and printed their subtotal
    // as "Total", inches above a table row headed All carrying a larger
    // number. Same rule as `DrillDownTable`: the total is the sum of the rows
    // listed, and a wider figure is drawn beside it.
    render(
      <ChartTooltip
        active
        payload={[
          { name: 'Rent', value: 1800 },
          { name: 'Groceries', value: 600 },
        ]}
        label="Sep 26"
        showTotal
        wider={{ total: 3200, label: 'categories' }}
        formatter={(v) => `$${v}`}
      />
    )
    // The drill table's wording, from the drill table's function: this
    // tooltip said "Shown" where the table says "Total of the N shown".
    expect(screen.getByText('Total of the 2 shown')).toBeInTheDocument()
    expect(screen.getByText('$2400')).toBeInTheDocument()
    expect(screen.getByText('All categories')).toBeInTheDocument()
    expect(screen.getByText('$3200')).toBeInTheDocument()
    expect(screen.queryByText('Total')).toBeNull()
  })

  it('still says "Total" when the drawn series are every series', () => {
    render(
      <ChartTooltip
        active
        payload={[
          { name: 'Rent', value: 1800 },
          { name: 'Groceries', value: 600 },
        ]}
        showTotal
        wider={{ total: 2400, label: 'categories' }}
        formatter={(v) => `$${v}`}
      />
    )
    expect(screen.getByText('Total')).toBeInTheDocument()
    expect(screen.queryByText('All categories')).toBeNull()
  })

  it('reads a rounding cent between its rows and the whole as the whole set', () => {
    // The tooltip carried its own `>= 0.005` literal beside the table's CENT;
    // it now asks `isPartial`, so the two cannot disagree about one set.
    render(
      <ChartTooltip
        active
        payload={[
          { name: 'Rent', value: 1800 },
          { name: 'Groceries', value: 600 },
        ]}
        showTotal
        wider={{ total: 2400.004, label: 'categories' }}
        formatter={(v) => `$${v}`}
      />
    )
    expect(screen.getByText('Total')).toBeInTheDocument()
    expect(screen.queryByText('All categories')).toBeNull()
  })
})
