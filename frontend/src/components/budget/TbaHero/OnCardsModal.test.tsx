/**
 * The breakdown behind the hero's "on cards" figure.
 *
 * The question it answers came from a real session: cover overspending, watch
 * the cash chip disappear, and find envelopes still red with nothing on the
 * page explaining which card is holding them.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import type { BudgetMonth } from '../../../types'

const month = vi.hoisted(() => ({ current: {} as Partial<BudgetMonth> }))
const peeked = vi.hoisted(() => ({ scope: null as unknown }))

vi.mock('../../../api/budgets', () => ({
  useBudgetMonth: () => ({ data: month.current }),
}))
vi.mock('../../../hooks/useMediaQuery', () => ({ useIsMobile: () => false }))
vi.mock('../TransactionsPeekModal/TransactionsPeekModal', () => ({
  TransactionsPeekModal: ({ scope }: { scope: unknown }) => {
    peeked.scope = scope
    return <div data-testid="peek" />
  },
}))

import { OnCardsModal } from './OnCardsModal'

function card(over: Record<string, unknown> = {}) {
  return {
    account_id: 'card-1',
    name: 'Sapphire Visa',
    overspent_this_month: 55,
    overspent_by_category: [
      { category_id: 'c-dining', category_name: 'Dining', amount: 35 },
      { category_id: 'c-groceries', category_name: 'Groceries', amount: 20 },
    ],
    ...over,
  }
}

beforeEach(() => {
  peeked.scope = null
  month.current = { cards: [card()] } as unknown as BudgetMonth
})

function open() {
  return render(<OnCardsModal budgetId="b1" month="2026-08-01" onClose={vi.fn()} />)
}

describe('OnCardsModal', () => {
  it('names the envelopes that rode onto the card', () => {
    open()
    expect(screen.getByText('Dining')).toBeInTheDocument()
    expect(screen.getByText('Groceries')).toBeInTheDocument()
    expect(screen.getByText('-$35.00')).toBeInTheDocument()
  })

  it('opens a single card, since a collapsed lone group says nothing', () => {
    open()
    expect(screen.getByRole('button', { name: /Sapphire Visa/ })).toHaveAttribute(
      'aria-expanded',
      'true'
    )
  })

  it('leaves several cards collapsed, and each one opens on its own', () => {
    month.current = {
      cards: [
        card(),
        card({
          account_id: 'card-2',
          name: 'Harborstone Mastercard',
          overspent_this_month: 10,
          overspent_by_category: [{ category_id: 'c-fun', category_name: 'Fun', amount: 10 }],
        }),
      ],
    } as unknown as BudgetMonth
    open()

    expect(screen.queryByText('Dining')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Sapphire Visa/ }))
    expect(screen.getByText('Dining')).toBeInTheDocument()
    // The other card stayed shut — the groups are independent.
    expect(screen.queryByText('Fun')).not.toBeInTheDocument()
  })

  it('shows each card total while the group is collapsed', () => {
    month.current = {
      cards: [card(), card({ account_id: 'card-2', name: 'Second' })],
    } as unknown as BudgetMonth
    open()
    expect(screen.getAllByText('-$55.00').length).toBeGreaterThan(0)
  })

  it('leaves out cards that carried no ride this month', () => {
    month.current = {
      cards: [card(), card({ account_id: 'card-2', name: 'Clean Card', overspent_this_month: 0 })],
    } as unknown as BudgetMonth
    open()
    expect(screen.queryByText(/Clean Card/)).not.toBeInTheDocument()
  })

  it('drills into one envelope rather than inventing per-transaction blame', () => {
    // The ride is a month's net, not a set of rows — so the row opens the
    // ordinary category peek instead of claiming these transactions rode.
    open()
    fireEvent.click(screen.getByRole('button', { name: 'Dining' }))
    expect(screen.getByTestId('peek')).toBeInTheDocument()
    expect(peeked.scope).toEqual({
      kind: 'category',
      categoryId: 'c-dining',
      categoryName: 'Dining',
    })
  })

  it('says the total and where the money has to come from', () => {
    open()
    expect(screen.getByText(/\$55\.00 of this month/)).toBeInTheDocument()
    expect(screen.getByText(/assigning to Sapphire Visa/)).toBeInTheDocument()
  })
})
