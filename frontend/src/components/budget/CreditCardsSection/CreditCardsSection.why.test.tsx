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

vi.mock('../../../api/budgets', () => ({
  useBudgetMonth: () => ({ data: month.current }),
  useSetAssignment: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock('../../../api/targets', () => ({ useTarget: () => ({ data: null }) }))
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

const door = (name = 'Sapphire Visa') =>
  screen.queryByRole('button', { name: `What is happening with ${name}` })

beforeEach(async () => {
  // Every test here opens a Dialog; drain the last one's deferred
  // history.back() or it closes the next test's dialog out from under it.
  await new Promise((r) => setTimeout(r, 0))
  await new Promise((r) => setTimeout(r, 0))
  window.history.replaceState(null, '')
  month.current = { cards: [paidAhead()], category_balances: [] } as unknown as BudgetMonth
})

describe('the explanation door', () => {
  it('is not there at all on a card with nothing to explain', () => {
    // The icon's presence IS the signal, so a funded card draws none — which
    // only works if a funded card really draws none.
    month.current = { cards: [card()], category_balances: [] } as unknown as BudgetMonth
    show()

    expect(door()).not.toBeInTheDocument()
  })

  it('appears on a card in a state worth explaining', () => {
    show()

    expect(door()).toBeInTheDocument()
  })

  it('keeps the explanation out of the strip until it is asked for', () => {
    // The complaint this replaced: a paragraph under every interesting card,
    // ballooning the table.
    show()

    expect(screen.queryByText(/more toward this card than any envelope/)).not.toBeInTheDocument()
  })

  it('opens a dialog headed by the card the sentence is about', async () => {
    // "Hard to know which card it refers to at a glance" — the heading is
    // the answer, and it has to carry the name.
    show()
    await userEvent.click(door() as HTMLElement)

    expect(screen.getByText('What is happening with Sapphire Visa')).toBeInTheDocument()
    expect(screen.getByText(/more toward this card than any envelope/)).toBeInTheDocument()
  })

  it('carries the action where the state has one', async () => {
    show()
    await userEvent.click(door() as HTMLElement)

    // Overspending on the card's envelope: squared this month, or covered by
    // next month's Ready to Assign — the same as any overspent envelope.
    expect(
      screen.getByText(/Assign \$300\.00 to the card this month, or it comes out of next month/)
    ).toBeInTheDocument()
  })

  it('never hides the sentence in a title attribute', async () => {
    // The original defect, by name: a `title` is unreachable on the installed
    // iOS PWA, which is the app's mobile target.
    show()
    await userEvent.click(door() as HTMLElement)

    const sentence = screen.getByText(/more toward this card than any envelope/)
    expect(sentence).not.toHaveAttribute('title')
  })

  it('opens the right card when several have something to say', async () => {
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
    await userEvent.click(door('Thistledown Card') as HTMLElement)

    expect(screen.getByText('What is happening with Thistledown Card')).toBeInTheDocument()
    expect(screen.getByText(/\$120\.00 more toward this card/)).toBeInTheDocument()
  })

  it('shows a reserve that does not add up in the same place', async () => {
    // The short "does not add up" chip stays on the row — it is the one
    // earned warning — and its sentence joins the rest behind the door.
    month.current = {
      cards: [paidAhead({ reserve_discrepancy: 42 })],
      category_balances: [],
    } as unknown as BudgetMonth
    show()
    await userEvent.click(door() as HTMLElement)

    expect(screen.getByText(/\$42\.00 of this Set aside is not explained/)).toBeInTheDocument()
  })
})
