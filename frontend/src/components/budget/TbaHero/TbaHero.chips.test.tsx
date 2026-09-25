/**
 * The overspending chip reads as "$120.00 overspent", not
 * "$120.00overspent" — and says the whole red, cards included.
 *
 * The chip is `display: inline-flex`, so the amount and the word are
 * separate flex items — and leading whitespace inside a flex item is
 * stripped. The separator was written as a literal space in the JSX, where it
 * had no effect; it now lives once, as `gap`, in TbaHero.css.
 *
 * So the assertion here is that the markup carries NO separator: jsdom does
 * not lay out `gap`, and a space reappearing in the JSX is exactly the
 * regression this pins. The CSS is where the space is allowed to come from.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import type { BudgetMonth } from '../../../types'

const month = vi.hoisted(() => ({ current: {} as Partial<BudgetMonth> }))

vi.mock('../../../api/budgets', () => ({
  useBudgetMonth: () => ({ data: month.current }),
}))
vi.mock('../../../api/categories', () => ({
  useCategories: () => ({
    data: [
      { id: 'dining', name: 'Dining' },
      { id: 'groc', name: 'Groceries' },
      { id: 'visa-env', name: 'Visa Payment' },
    ],
  }),
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

describe('TbaHero overspending chip', () => {
  it('puts no separator in the markup — the space is the flex gap', () => {
    render(<TbaHero budgetId="b1" month="2026-08-01" />)

    const span = screen.getByText('overspent')
    expect(span.textContent).toBe('overspent')
    expect(span.className).toContain('tba-hero__chip-word')
    expect(span.parentElement?.textContent).toBe('-$120.00overspent')
  })

  it('leaves the card part to the cards', () => {
    // A second "of it on cards" chip and its dialog sat here, beside a
    // figure it was a part of. That part is card debt, not money out of
    // Ready to Assign, so it moved to the cards band and each card's detail,
    // where assigning to the card is one tap away. One chip covers it all.
    render(<TbaHero budgetId="b1" month="2026-08-01" />)
    expect(screen.queryByText(/on cards/)).toBeNull()
    expect(screen.getAllByRole('button', { name: /overspent/ })).toHaveLength(1)
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
  })
})

describe('what the 1st took out of Ready to Assign', () => {
  // Ready to Assign always dropped by last month's overspending on the 1st,
  // and nothing on the page said why. The header says how much, as a pill
  // like the overspent one; the envelopes are one tap away. It was a sentence
  // listing them all, which wrapped into two ragged lines under the number.
  function withLastMonth() {
    month.current = {
      to_be_assigned: 800,
      total_overspent: 0,
      total_overspent_credit: 0,
      overspent_last_month: [
        { category_id: 'visa-env', amount: 100 },
        { category_id: 'dining', amount: 50 },
        { category_id: 'groc', amount: 20 },
        { category_id: 'gone', amount: 5 },
      ],
      cards: [{ category_id: 'visa-env', name: 'Sapphire Visa' }],
    } as unknown as BudgetMonth
  }

  it('carries the total in the header, and nothing else', () => {
    withLastMonth()
    render(<TbaHero budgetId="b1" month="2026-08-01" />)
    const pill = screen.getByRole('button', { name: /overspent last month/ })
    expect(pill.textContent).toBe('-$175.00overspent last month')
    expect(screen.queryByText(/Dining/)).toBeNull()
  })

  it('opens every envelope, named, not a top few', () => {
    withLastMonth()
    render(<TbaHero budgetId="b1" month="2026-08-01" />)
    fireEvent.click(screen.getByRole('button', { name: /overspent last month/ }))
    const dialog = screen.getByRole('dialog', { name: 'Overspent in July 2026' })
    // A card's envelope is named for its card.
    for (const [name, amount] of [
      ['Sapphire Visa', '-$100.00'],
      ['Dining', '-$50.00'],
      ['Groceries', '-$20.00'],
      ['An envelope', '-$5.00'],
      ['Total', '-$175.00'],
    ]) {
      const row = within(dialog).getByText(name).closest('.envelope-list__row') as HTMLElement
      expect(row.textContent).toContain(amount)
    }
  })

  it('says nothing when nothing was absorbed', () => {
    month.current = {
      to_be_assigned: 800,
      total_overspent: 0,
      total_overspent_credit: 0,
      overspent_last_month: [],
    } as unknown as BudgetMonth
    render(<TbaHero budgetId="b1" month="2026-08-01" />)
    expect(screen.queryByText(/last month/)).toBeNull()
  })
})
