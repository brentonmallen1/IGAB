/**
 * What a card owes, on its folded line; and what set its money aside, one tap
 * from the figure.
 *
 * The folded line drew a word, a bar and the Set aside pill, and never the
 * debt — "I only see the amount that's been set aside". It says Owes now,
 * the same figure the opened card does (`cardCoverage`).
 *
 * Covered was a plain figure: there was no way from it to the charges that
 * set the money aside, where every envelope's Activity opens its rows. It is
 * a button now, as is the breakdown's Set aside total, and both open the
 * card-reserve peek for the viewed month.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { BudgetMonth, CardStatus } from '../../../types'

const month = vi.hoisted(() => ({ current: {} as Partial<BudgetMonth> }))
const peeked = vi.hoisted(() => ({ scope: null as unknown }))

vi.mock('../../../api/budgets', () => ({
  useBudgetMonth: () => ({ data: month.current }),
  useSetAssignment: () => ({ mutate: vi.fn(), isPending: false }),
  useCardTimeline: () => ({ data: undefined, isPending: true, isError: false }),
}))
vi.mock('../../../api/targets', () => ({ useTarget: () => ({ data: null }) }))
vi.mock('../../../api/accounts', () => ({ useAccounts: () => ({ data: [] }) }))
vi.mock('../../../api/liabilities', () => ({ useLiabilities: () => ({ data: [] }) }))
vi.mock('../../../api/categories', () => ({ useCategories: () => ({ data: [] }) }))
vi.mock('../TargetEditor', () => ({ TargetEditor: () => null }))
vi.mock('../TransactionsPeekModal/TransactionsPeekModal', () => ({
  TransactionsPeekModal: ({ scope }: { scope: unknown }) => {
    peeked.scope = scope
    return <div data-testid="peek" />
  },
}))
vi.mock('../../../api/cardDueDismissals', () => ({ useCardDueDismissals: () => ({ data: [] }) }))
vi.mock('../../../hooks/useMarkBillPaid', () => ({
  useMarkBillPaid: () => ({ mark: vi.fn(), isPending: false }),
}))

import { CreditCardsSection } from './CreditCardsSection'
import { cardStatus } from '../../../test-utils/cardFixture'

/** Owes 1,240 with 300 set aside: a quarter of it covered. */
function card(over: Partial<CardStatus> = {}): CardStatus {
  return cardStatus({ balance: -1240, set_aside: 300, reserved: 300, ...over })
}

function show() {
  render(<CreditCardsSection budgetId="b1" month="2026-09-01" />)
}

async function openCard() {
  await userEvent.click(screen.getByRole('button', { name: /^Sapphire Visa/ }))
}

beforeEach(() => {
  peeked.scope = null
  month.current = { cards: [card()], category_balances: [] } as unknown as BudgetMonth
})

describe('the folded line', () => {
  it('says what the card owes beside what is set aside for it', () => {
    show()
    const line = screen.getByRole('button', { name: /^Sapphire Visa/ })
    expect(line).toHaveTextContent('Owes $1,240.00')
    expect(line).toHaveTextContent('$300.00')
  })

  it('owes nothing on a card paid off or in credit, rather than a negative debt', () => {
    month.current = {
      cards: [card({ balance: 75, set_aside: 0, reserved: 0, set_aside_state: 'card_holds_it' })],
      category_balances: [],
    } as unknown as BudgetMonth
    show()
    expect(screen.getByRole('button', { name: /^Sapphire Visa/ })).toHaveTextContent('Owes $0.00')
  })

  it('agrees with the opened card’s Owes and Covered — one spelling of both', async () => {
    show()
    await openCard()
    const owes = screen.getByText('Owes', { selector: 'dt' }).nextElementSibling
    expect(owes?.textContent).toBe('$1,240.00')
    expect(screen.getByRole('button', { name: /^Covered: \$300\.00/ })).toBeInTheDocument()
  })
})

describe('what set this money aside', () => {
  it('opens from Covered, for this card and the viewed month', async () => {
    show()
    await openCard()
    await userEvent.click(screen.getByRole('button', { name: /^Covered:/ }))

    expect(peeked.scope).toEqual({
      kind: 'card-reserve',
      accountId: card().account_id,
      accountName: 'Sapphire Visa',
      month: '2026-09-01',
    })
  })

  it('opens from the keyboard too', async () => {
    show()
    await openCard()
    screen.getByRole('button', { name: /^Covered:/ }).focus()
    await userEvent.keyboard('{Enter}')

    expect(peeked.scope).toMatchObject({ kind: 'card-reserve' })
  })

  it('opens from the breakdown’s Set aside total', async () => {
    show()
    await openCard()
    await userEvent.click(screen.getByRole('button', { name: /What makes up Set aside/ }))
    await userEvent.click(screen.getByRole('button', { name: /^Set aside for Sapphire Visa/ }))

    expect(peeked.scope).toMatchObject({ kind: 'card-reserve', month: '2026-09-01' })
  })
})
