/**
 * MetricCard's one clickable-card mechanism (`details`). The means card built
 * it privately; the savings-rate cards use the same one.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { MetricCard } from './MetricCard'

describe('MetricCard details', () => {
  it('is a plain figure without details — no button, no affordance', () => {
    const { container } = render(<MetricCard label="Income" value="$5,000.00" />)
    expect(screen.queryByRole('button')).toBeNull()
    expect(container.querySelector('.metric-card--opens')).toBeNull()
    expect(container.querySelector('.metric-card__opens-icon')).toBeNull()
  })

  it('wraps the value in a button named by the label it is given', async () => {
    const onOpen = vi.fn()
    const { container } = render(
      <MetricCard
        label="Savings Rate"
        value="18.5%"
        details={{ label: 'Savings rate 18.5%. Show what contributed', onOpen }}
      />
    )

    const button = screen.getByRole('button', { name: 'Savings rate 18.5%. Show what contributed' })
    expect(button).toHaveAttribute('aria-haspopup', 'dialog')
    expect(button).toHaveTextContent('18.5%')
    expect(container.querySelector('.metric-card')).toHaveClass('metric-card--opens')
    await userEvent.click(button)
    expect(onOpen).toHaveBeenCalledOnce()
  })

  it('keeps the affordance and the delta together on a card with a delta', () => {
    const { container } = render(
      <MetricCard
        label="Net Worth"
        value="$1,100.00"
        delta={{ value: 10, label: 'vs prior period' }}
        details={{ label: 'Net worth. Show more', onOpen: () => {} }}
      />
    )
    expect(container.querySelector('.metric-card__label .metric-card__opens-icon')).not.toBeNull()
    expect(screen.getByText(/\+10\.0%/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Net worth. Show more' })).toHaveTextContent(
      '$1,100.00'
    )
  })

  it('opens from the keyboard', async () => {
    const onOpen = vi.fn()
    render(<MetricCard label="Savings Rate" value="—" details={{ label: 'Open', onOpen }} />)
    await userEvent.tab()
    expect(screen.getByRole('button', { name: 'Open' })).toHaveFocus()
    await userEvent.keyboard('{Enter}')
    expect(onOpen).toHaveBeenCalledOnce()
  })
})
