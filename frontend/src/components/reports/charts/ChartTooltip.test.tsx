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
import type { ComponentProps } from 'react'
import { render, renderHook, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ChartTooltip } from './ChartTooltip'
import { rateTooltip } from './savingsRateView'
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
    // A chart whose series are in two units — money bars and a percentage
    // line — branches on the name. The shared default rendered a rate of
    // 18.5 as "$18.50".
    const { formatMoney } = renderHook(() => useFormatters()).result.current
    render(
      <ChartTooltip
        active
        payload={[
          { name: 'Saved', value: 900 },
          { name: 'Rate', value: 18.5 },
        ]}
        formatter={(v, name) => (name === 'Rate' ? rateTooltip(v) : formatMoney(v))}
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

// The `wider` prop is gone: no chart passed it. Pinned at the type level, so
// it cannot come back unused — tsc fails this line while the prop exists.
type TooltipHasWider = 'wider' extends keyof ComponentProps<typeof ChartTooltip> ? true : false
const tooltipHasNoWider: TooltipHasWider = false

describe('ChartTooltip props', () => {
  it('takes no wider set: every stack it totals is drawn whole', () => {
    expect(tooltipHasNoWider).toBe(false)
  })
})
