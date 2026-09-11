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
import { render, renderHook, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ChartTooltip } from './ChartTooltip'
import { RATE_SERIES, savingsRateTooltipWith } from './savingsRateView'
import { useFormatters } from '../../../hooks/useFormatters'
import { useAppStore } from '../../../stores/appStore'

afterEach(() => {
  useAppStore.setState({ privacyMode: false })
})

describe('ChartTooltip', () => {
  it('renders exactly what the formatter returns, adding no currency of its own', () => {
    render(
      <ChartTooltip
        active
        payload={[{ name: 'Net Worth', value: -1200 }]}
        formatter={(v) => `-€${Math.abs(v).toFixed(2)}`}
      />
    )
    // A passed formatter always won, even over the old default; what this
    // pins is that the tooltip adds no currency or sign of its own around it.
    expect(screen.getByText('-€1200.00')).toBeInTheDocument()
    expect(screen.queryByText(/\$/)).toBeNull()
  })

  it('masks through the formatMoney the charts hand it, in privacy mode', () => {
    // Not a literal mask echoed back: the charts pass useFormatters()'s
    // formatMoney, so that is what this renders — with privacy mode on, the
    // fund and the total must both come out masked.
    useAppStore.setState({ privacyMode: true })
    const { formatMoney } = renderHook(() => useFormatters()).result.current
    render(
      <ChartTooltip
        active
        showTotal
        payload={[
          { name: 'Fund', value: 412880.5 },
          { name: 'Reserve', value: 1200 },
        ]}
        formatter={formatMoney}
      />
    )
    expect(screen.getAllByText('$••••')).toHaveLength(3)
    expect(screen.queryByText(/412|880|1,?200|414/)).toBeNull()
  })

  it('passes the series name, so one tooltip can serve two units', () => {
    // SavingsRateChart's own formatter: money bars plus a percentage line. The
    // shared default rendered the rate 18.5 as "$18.50".
    const { formatMoney } = renderHook(() => useFormatters()).result.current
    render(
      <ChartTooltip
        active
        payload={[
          { name: 'Saved', value: 900 },
          { name: RATE_SERIES, value: 18.5 },
        ]}
        formatter={savingsRateTooltipWith(formatMoney)}
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
