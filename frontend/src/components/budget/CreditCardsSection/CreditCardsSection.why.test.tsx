/**
 * Why a card reads the way it does — one tap from the card it is about.
 *
 * These sentences started life as `title` attributes, which an installed iOS
 * PWA never renders, so nobody on a phone could read them. The fix put them
 * in the document as a paragraph row under each card row, which ballooned the
 * strip and left a block of prose sitting between two rows belonging at a
 * glance to neither.
 *
 * So: a real button beside the card's name, and a dialog headed by that name.
 * Both halves are load-bearing — a tooltip fails the phone, and an unheaded
 * dialog fails the "which card is this about" question that sent it here.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { BudgetMonth, CardStatus } from '../../../types'

const month = vi.hoisted(() => ({ current: {} as Partial<BudgetMonth> }))

const accounts = vi.hoisted(() => ({
  current: [] as { id: string; uncategorized_count: number }[],
}))
vi.mock('../../../api/budgets', () => ({
  useBudgetMonth: () => ({ data: month.current }),
  useSetAssignment: () => ({ mutate: vi.fn(), isPending: false }),
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
    expect(screen.queryByText(/more toward this card than any envelope/)).not.toBeInTheDocument()
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
    expect(detail?.textContent).toMatch(/more toward this card than any envelope/)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('carries the action where the state has one', async () => {
    show()
    await userEvent.click(line())

    // Overspending on the card's envelope: squared this month, or covered by
    // next month's Ready to Assign — the same as any overspent envelope.
    expect(
      screen.getByText(/Assign \$300\.00 to the card this month, or it comes out of next month/)
    ).toBeInTheDocument()
  })

  it('says something plain about a calm card, too', async () => {
    month.current = { cards: [card()], category_balances: [] } as unknown as BudgetMonth
    show()
    await userEvent.click(line())
    expect(screen.getByText(/isn.t set aside yet/)).toBeInTheDocument()
  })

  it('never hides the sentence in a title attribute', async () => {
    // The original defect, by name: a `title` is unreachable on the installed
    // iOS PWA, which is the app's mobile target.
    show()
    await userEvent.click(line())

    const sentence = screen.getByText(/more toward this card than any envelope/)
    expect(sentence).not.toHaveAttribute('title')
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

    expect(screen.getByText(/\$120\.00 more toward this card/)).toBeInTheDocument()
    expect(screen.queryByText(/\$300\.00 more toward this card/)).not.toBeInTheDocument()
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
