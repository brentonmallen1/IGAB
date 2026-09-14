/**
 * The Means trend chart, drawn for real at a fixed size. jsdom has no layout,
 * so `ResponsiveContainer` measures zero and draws nothing; it is swapped for
 * a fixed-size one. Colour is CSS (MeansStanding.css) — what is pinned here is
 * that each bar carries its month's standing class, a month with no income
 * draws no bar, and the band and zero line are drawn.
 */
import { render } from '@testing-library/react'
import { cloneElement, type ReactElement } from 'react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('recharts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('recharts')>()
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: ReactElement<object> }) =>
      cloneElement(children, { width: 600, height: 240 } as object),
  }
})

import { meansTrend } from './livingMeans'
import { MeansTrendChart } from './MeansTrendChart'

const trend = meansTrend([
  { month: '2026-01-01', income: 5000, outflows: 4400 }, // 12% kept: below
  { month: '2026-02-01', income: 5000, outflows: 5200 }, // 4% over: at
  { month: '2026-03-01', income: 1000, outflows: 3500 }, // 250% over: above, clamped
  { month: '2026-04-01', income: 0, outflows: 300 }, // no income: no bar
])

describe('MeansTrendChart', () => {
  it('draws one bar per month with income, classed by its standing', () => {
    const { container } = render(<MeansTrendChart trend={trend} formatMonth={(m) => m} />)
    const bars = [...container.querySelectorAll('.means-trend-chart__bar')]
    expect(bars.map((b) => b.getAttribute('class'))).toEqual([
      expect.stringContaining('means-standing--below'),
      expect.stringContaining('means-standing--at'),
      expect.stringContaining('means-standing--above'),
    ])
    expect(container.querySelector('.means-trend-chart__band')).not.toBeNull()
    expect(container.querySelector('.means-trend-chart__zero')).not.toBeNull()
    // The full chart states the axis in percent.
    expect(container.textContent).toContain('100%')
  })

  it('draws the strip without axes, named by its caller', () => {
    const { container, getByRole } = render(
      <MeansTrendChart trend={trend} formatMonth={(m) => m} variant="strip" label="Strip" />
    )
    expect(getByRole('img', { name: 'Strip' })).toBeInTheDocument()
    expect(container.querySelectorAll('.means-trend-chart__bar')).toHaveLength(3)
    expect(container.textContent).not.toContain('%')
  })

  it('hides an unnamed chart from assistive technology — its table says it all', () => {
    const { container } = render(<MeansTrendChart trend={trend} formatMonth={(m) => m} />)
    expect(container.firstElementChild).toHaveAttribute('aria-hidden', 'true')
  })
})
