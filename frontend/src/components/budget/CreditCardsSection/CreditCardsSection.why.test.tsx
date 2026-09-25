/**
 * Why a card reads the way it does — one tap from the card it is about.
 *
 * These sentences started life as `title` attributes, which an installed iOS
 * PWA never renders; then a paragraph under every row, which ballooned the
 * strip; then a dialog; then paragraphs under an opened line, which were too
 * much to read to be read at all. Now: tap the line and it opens in place to
 * three figures and, only when something is off, one callout — a headline,
 * one line of cause, and the fix as a button.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { BudgetMonth, CardStatus } from '../../../types'

const month = vi.hoisted(() => ({ current: {} as Partial<BudgetMonth> }))

const accounts = vi.hoisted(() => ({
  current: [] as { id: string; uncategorized_count: number }[],
}))
const mutate = vi.hoisted(() => vi.fn())
vi.mock('../../../api/budgets', () => ({
  useBudgetMonth: () => ({ data: month.current }),
  useSetAssignment: () => ({ mutate, isPending: false }),
}))
vi.mock('../../../api/targets', () => ({ useTarget: () => ({ data: null }) }))
vi.mock('../../../api/accounts', () => ({ useAccounts: () => ({ data: accounts.current }) }))
vi.mock('../../../api/liabilities', () => ({ useLiabilities: () => ({ data: [] }) }))
vi.mock('../../../api/categories', () => ({ useCategories: () => ({ data: [] }) }))
vi.mock('../TargetEditor', () => ({ TargetEditor: () => null }))
vi.mock('../TransactionsPeekModal/TransactionsPeekModal', () => ({
  TransactionsPeekModal: () => null,
}))

import { CreditCardsSection } from './CreditCardsSection'
import { cardStatus } from '../../../test-utils/cardFixture'

function card(over: Partial<CardStatus> = {}): CardStatus {
  return cardStatus({ balance: -600, ...over })
}

/** A card paid further than any envelope set aside for it — a state with
 *  both a sentence and an action. */
function paidAhead(over: Partial<CardStatus> = {}): CardStatus {
  return card({
    set_aside: -300,
    short_reserved: 300,
    payments: 300,
    set_aside_state: 'paid_ahead',
    ...over,
  })
}

function show() {
  render(<CreditCardsSection budgetId="b1" month="2026-08-01" />)
}

const line = (name = 'Sapphire Visa') =>
  screen.getByRole('button', { name: new RegExp(`^${name}`) })

beforeEach(() => {
  month.current = { cards: [paidAhead()], category_balances: [] } as unknown as BudgetMonth
})

describe('a card opens in place', () => {
  it('keeps the explanation out of the strip until the card is opened', () => {
    // The complaint that moved it behind a dialog: a paragraph under every
    // interesting card, ballooning the table. One line each, until tapped.
    show()
    expect(screen.queryByText(/Overspent by/)).not.toBeInTheDocument()
    expect(line()).toHaveAttribute('aria-expanded', 'false')
  })

  it('marks a card that needs you, before anyone opens it', () => {
    show()
    expect(screen.getByText('overspent')).toBeInTheDocument()
    expect(document.querySelector('.credit-cards__mark--overspent')).not.toBeNull()
  })

  it('draws no mark on a card with nothing to do', () => {
    month.current = { cards: [card()], category_balances: [] } as unknown as BudgetMonth
    show()
    expect(document.querySelector('.credit-cards__mark')).toBeNull()
    expect(screen.getByText('$600.00 not covered')).toBeInTheDocument()
  })

  it('opens under its own line, not in a dialog', async () => {
    show()
    await userEvent.click(line())

    expect(line()).toHaveAttribute('aria-expanded', 'true')
    const detail = document.getElementById(line().getAttribute('aria-controls') as string)
    expect(detail).not.toBeNull()
    expect(detail?.textContent).toMatch(/Overspent by \$300\.00/)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('makes the fix a button that does it', async () => {
    // It was a sentence telling you to go and assign $300. The button
    // assigns it: this month's assignment on the card, raised by exactly
    // the shortfall — the same mutation the Assigned field uses, undo and all.
    month.current = {
      cards: [paidAhead()],
      category_balances: [{ category_id: 'c1', assigned: 50 }],
    } as unknown as BudgetMonth
    show()
    await userEvent.click(line())
    await userEvent.click(screen.getByRole('button', { name: 'Assign $300.00' }))
    expect(mutate).toHaveBeenCalledWith({
      categoryId: 'c1',
      month: '2026-08-01',
      amount: 350,
    })
    // And what happens if nobody presses it.
    expect(screen.getByText(/Otherwise it comes out of next month.s Ready to Assign/)).toBeTruthy()
  })

  it('opens a calm card to its figures, with nothing to read', async () => {
    // Debt not covered is information: the three figures say it, and a
    // paragraph restating them was the wall of text people stopped reading.
    month.current = { cards: [card()], category_balances: [] } as unknown as BudgetMonth
    show()
    await userEvent.click(line())
    const stats = document.querySelector('.credit-cards__stats') as HTMLElement
    expect(stats.textContent).toBe('Owes$600.00Covered$0.00Not covered$600.00')
    expect(document.querySelector('.credit-cards__callout')).toBeNull()
  })

  it('never hides the headline in a title attribute', async () => {
    // The original defect, by name: a `title` is unreachable on the installed
    // iOS PWA, which is the app's mobile target.
    show()
    await userEvent.click(line())

    expect(screen.getByText('Overspent by $300.00')).not.toHaveAttribute('title')
  })

  it('opens the right card, one at a time', async () => {
    month.current = {
      cards: [
        paidAhead(),
        paidAhead({
          account_id: 'a2',
          name: 'Thistledown Card',
          category_id: 'c2',
          set_aside: -120,
          short_reserved: 120,
        }),
      ],
      category_balances: [],
    } as unknown as BudgetMonth
    show()
    await userEvent.click(line())
    await userEvent.click(line('Thistledown Card'))

    expect(screen.getByText('Overspent by $120.00')).toBeInTheDocument()
    expect(screen.queryByText('Overspent by $300.00')).not.toBeInTheDocument()
    expect(line()).toHaveAttribute('aria-expanded', 'false')
  })

  it('shows a reserve that does not add up in the same place', async () => {
    month.current = {
      cards: [paidAhead({ reserve_discrepancy: 42 })],
      category_balances: [],
    } as unknown as BudgetMonth
    show()
    await userEvent.click(line())

    expect(screen.getByText(/\$42\.00 of this Set aside is not explained/)).toBeInTheDocument()
  })
})
