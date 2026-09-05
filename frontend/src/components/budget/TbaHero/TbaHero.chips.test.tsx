/**
 * The two overspending chips read as "$120.00 overspent", not
 * "$120.00overspent" — and say the right two numbers.
 *
 * Both chips are `display: inline-flex`, so the amount and the word are
 * separate flex items — and leading whitespace inside a flex item is
 * stripped. The separator was written as a literal space in the JSX, where it
 * had no effect; it now lives once, as `gap`, in TbaHero.css.
 *
 * So the assertion here is that the markup carries NO separator: jsdom does
 * not lay out `gap`, and a space reappearing in the JSX is exactly the
 * regression this pins. The CSS is where the space is allowed to come from.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import type { BudgetMonth } from '../../../types'

const month = vi.hoisted(() => ({ current: {} as Partial<BudgetMonth> }))

vi.mock('../../../api/budgets', () => ({
  useBudgetMonth: () => ({ data: month.current }),
}))
vi.mock('../../../hooks/useMediaQuery', () => ({ useIsMobile: () => false }))
vi.mock('../AssignDropdown/AssignDropdown', () => ({
  AssignDropdown: () => null,
  AssignDropdownContent: () => null,
}))
vi.mock('../AssignPreviewModal/AssignPreviewModal', () => ({
  AssignPreviewModal: () => null,
}))
vi.mock('./CoverOverspentModal', () => ({ CoverOverspentModal: () => null }))
vi.mock('./OnCardsModal', () => ({
  OnCardsModal: ({ onClose }: { onClose: () => void }) => (
    <div role="dialog" aria-label="Overspending on cards">
      <button onClick={onClose}>Close</button>
    </div>
  ),
}))
vi.mock('./TbaDrawer', () => ({ TbaDrawer: () => null }))

import { TbaHero } from './TbaHero'

beforeEach(() => {
  // 120 red in all, 45 of it swiped on a card. The chip is the whole red —
  // it counted only the cash part until 2026-09-05, so covering made it
  // vanish while the grid still drew red envelopes.
  month.current = {
    to_be_assigned: 0,
    total_overspent: 120.0,
    total_overspent_cash: 75.0,
    total_overspent_credit: 45.0,
    overspent_count: 1,
    overspent_count_cash: 1,
  } as unknown as BudgetMonth
})

describe('TbaHero overspending chips', () => {
  it('puts no separator in the markup — the space is the flex gap', () => {
    render(<TbaHero budgetId="b1" month="2026-08-01" />)

    for (const word of ['overspent', 'of it on cards']) {
      const span = screen.getByText(word)
      expect(span.textContent).toBe(word)
      expect(span.className).toContain('tba-hero__chip-word')
    }
  })

  it('still renders both amounts beside their words', () => {
    render(<TbaHero budgetId="b1" month="2026-08-01" />)

    expect(screen.getByText('overspent').parentElement?.textContent).toBe('-$120.00overspent')
    expect(screen.getByText('of it on cards').parentElement?.textContent).toBe(
      '-$45.00of it on cards'
    )
  })

  it('opens the card breakdown from the on-cards chip', async () => {
    // The chip used to be a dead span. It is the only way into the figure
    // Cover Overspending deliberately will not touch.
    render(<TbaHero budgetId="b1" month="2026-08-01" />)

    fireEvent.click(screen.getByText('of it on cards').closest('button')!)
    expect(screen.getByRole('dialog', { name: 'Overspending on cards' })).toBeInTheDocument()
  })

  it('counts the whole red, not the cash part', () => {
    // The regression that started this: the chip vanished after covering
    // while the grid still drew red envelopes, because it read the cash-only
    // total. Cover Overspending funds both parts now.
    render(<TbaHero budgetId="b1" month="2026-08-01" />)
    expect(screen.getByText('overspent').parentElement?.textContent).toContain('$120.00')
  })

  it('says nothing when nothing is overspent', () => {
    month.current = { to_be_assigned: 0 } as unknown as BudgetMonth
    render(<TbaHero budgetId="b1" month="2026-08-01" />)

    expect(screen.queryByText('overspent')).toBeNull()
    expect(screen.queryByText('of it on cards')).toBeNull()
  })
})
