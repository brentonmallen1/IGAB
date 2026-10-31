import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { BudgetColorsPicker } from './BudgetColorsPicker'

describe('BudgetColorsPicker', () => {
  it('draws each mode as its own preview, whatever the app is set to', () => {
    // The attribute on each card is what scopes base.css's figure variables
    // to it — without it every card would show the current mode.
    render(<BudgetColorsPicker value="full" onChange={vi.fn()} />)
    const cards = screen.getAllByRole('radio').map((r) => r.closest('label'))
    expect(cards.map((c) => c?.getAttribute('data-budget-colors'))).toEqual([
      'full',
      'available',
      'none',
    ])
  })

  it('samples every reading through the grid’s own figure classes', () => {
    const { container } = render(<BudgetColorsPicker value="full" onChange={vi.fn()} />)
    const first = container.querySelector('[data-budget-colors="full"]')!
    expect(first.querySelector('.budget-figure--flow.negative')).not.toBeNull()
    expect(first.querySelector('.budget-figure--flow.positive')).not.toBeNull()
    expect(first.querySelector('.budget-figure--balance.positive')).not.toBeNull()
    expect(first.querySelector('.budget-figure--balance.negative')).not.toBeNull()
    expect(first.querySelector('.budget-figure--balance.negative-on-card')).not.toBeNull()
    expect(first.querySelector('.budget-colors__row--overspent')).not.toBeNull()
  })

  it('marks the current mode and reports a choice', () => {
    const onChange = vi.fn()
    render(<BudgetColorsPicker value="available" onChange={onChange} />)
    expect(screen.getByRole('radio', { name: /Available only/ })).toBeChecked()
    fireEvent.click(screen.getByRole('radio', { name: /No colour/ }))
    expect(onChange).toHaveBeenCalledWith('none')
  })
})
