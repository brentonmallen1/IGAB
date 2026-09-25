/**
 * This month's overspending that rode onto a card, said on the cards.
 *
 * It sat in the Ready to Assign header as a second chip ("of it on cards")
 * with its own dialog, beside the overspent chip it was a part of. It is card
 * debt, not money out of Ready to Assign, so it moved: the band says how much
 * rode on this month, and an opened card says how much and from how many
 * envelopes, next to the assigned box that retires it. The envelopes were
 * named inline on that line until a long month wrapped it into a paragraph;
 * they are one tap away now, in the same list dialog the header uses for
 * last month's overspending.
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { BudgetMonth, CardStatus } from '../../../types'

const month = vi.hoisted(() => ({ current: {} as Partial<BudgetMonth> }))
const peeked = vi.hoisted(() => ({ scope: null as unknown }))

vi.mock('../../../api/budgets', () => ({
  useBudgetMonth: () => ({ data: month.current }),
  useSetAssignment: () => ({ mutate: vi.fn(), isPending: false }),
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

import { CreditCardsSection } from './CreditCardsSection'
import { cardStatus } from '../../../test-utils/cardFixture'

function card(over: Partial<CardStatus> = {}): CardStatus {
  return cardStatus({
    balance: -600,
    set_aside: 0,
    overspent_this_month: 55,
    ride_reaches_this_card: true,
    overspent_by_category: [
      { category_id: 'c-dining', category_name: 'Dining', amount: 35 },
      { category_id: 'c-groceries', category_name: 'Groceries', amount: 20 },
    ],
    ...over,
  })
}

function show() {
  render(<CreditCardsSection budgetId="b1" month="2026-08-01" />)
}

async function openCard(name = 'Sapphire Visa') {
  await userEvent.click(screen.getByRole('button', { name: new RegExp(`^${name}`) }))
}

beforeEach(() => {
  peeked.scope = null
  month.current = {
    cards: [card()],
    category_balances: [],
    total_overspent: 80,
    total_overspent_credit: 55,
  } as unknown as BudgetMonth
})

describe('the band', () => {
  it('says how much rode on this month', () => {
    show()
    expect(screen.getByTestId('credit-cards-band').textContent).toContain(
      '$55.00 rode on this month'
    )
  })

  it('shows the served total, not a sum of the card rows', () => {
    // The dialog's headline re-added the card rows once, and agreed with the
    // chip only for reasons written and tested nowhere: a card the summary
    // skips — settled and closed — takes the sum below the served figure.
    // The numbers disagree on purpose; the band follows the server.
    month.current = { ...month.current, total_overspent_credit: 90 }
    show()
    expect(screen.getByTestId('credit-cards-band').textContent).toContain(
      '$90.00 rode on this month'
    )
  })

  it('says nothing about rides in a month with none', () => {
    month.current = {
      cards: [card({ overspent_this_month: 0, overspent_by_category: [] })],
      category_balances: [],
      total_overspent_credit: 0,
    } as unknown as BudgetMonth
    show()
    expect(screen.getByTestId('credit-cards-band').textContent).not.toContain('rode')
  })
})

describe('an opened card', () => {
  it('says how much rode on, from how many envelopes, on one line', async () => {
    show()
    await openCard()
    // A total and a count, however many envelopes there are — no remedy
    // prose: the assigned field right under it is the remedy.
    const said = screen.getByText(/rode on this month from/)
    expect(said.textContent).toBe('$55.00 rode on this month from 2 envelopesShow')
    expect(screen.queryByText('Dining')).toBeNull()
  })

  it('counts one envelope in the singular', async () => {
    month.current = {
      cards: [
        card({
          overspent_this_month: 35,
          overspent_by_category: [{ category_id: 'c-dining', category_name: 'Dining', amount: 35 }],
        }),
      ],
      category_balances: [],
    } as unknown as BudgetMonth
    show()
    await openCard()
    expect(screen.getByText(/rode on this month from/).textContent).toContain('from 1 envelope')
  })

  it('lists every envelope and the total behind Show', async () => {
    show()
    await openCard()
    await userEvent.click(screen.getByRole('button', { name: 'Show' }))
    const dialog = screen.getByRole('dialog', { name: 'Rode on Sapphire Visa in August 2026' })
    for (const [name, amount] of [
      ['Dining', '$35.00'],
      ['Groceries', '$20.00'],
      ['Total', '$55.00'],
    ]) {
      const row = within(dialog).getByText(name).closest('.envelope-list__row') as HTMLElement
      expect(row.textContent).toContain(amount)
    }
  })

  it('says nothing about rides on a card that carried none', async () => {
    month.current = {
      cards: [card({ overspent_this_month: 0, overspent_by_category: [] })],
      category_balances: [],
    } as unknown as BudgetMonth
    show()
    await openCard()
    expect(screen.queryByText(/Rode on this month/)).toBeNull()
  })

  it('opens one envelope rather than blaming particular transactions', async () => {
    // The ride is a month's net, not a set of rows — so the name opens the
    // ordinary category peek instead of claiming these transactions rode.
    show()
    await openCard()
    await userEvent.click(screen.getByRole('button', { name: 'Show' }))
    await userEvent.click(screen.getByRole('button', { name: 'Dining' }))
    // The list gives way to the envelope's transactions rather than stacking.
    expect(screen.queryByRole('dialog', { name: /^Rode on/ })).toBeNull()
    expect(screen.getByTestId('peek')).toBeInTheDocument()
    expect(peeked.scope).toEqual({
      kind: 'category',
      categoryId: 'c-dining',
      categoryName: 'Dining',
    })
  })
})
