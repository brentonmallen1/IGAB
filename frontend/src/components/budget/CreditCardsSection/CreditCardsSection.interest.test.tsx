/**
 * Interest & fees, drawn under the cards.
 *
 * An ordinary envelope the server places in the Credit cards section
 * (`in_card_section`, served). The section draws it with the grid's own row,
 * so it is assigned, spent from and covered exactly like any envelope — and
 * draws nothing for it when it is archived (the category list leaves those
 * out) or folded away.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CreditCardsSection } from './CreditCardsSection'
import type { BudgetMonth, Category, CategoryBalance } from '../../../types'
import { cardStatus } from '../../../test-utils/cardFixture'
import { makeCategory } from '../../../test-utils/factories'

const month: { current: BudgetMonth | undefined } = { current: undefined }
const state = vi.hoisted(() => ({
  categories: [] as unknown[],
  collapsed: false,
  accounts: [] as { id: string; uncategorized_count: number }[],
}))

vi.mock('../../../api/budgets', () => ({
  useBudgetMonth: () => ({ data: month.current }),
  useSetAssignment: () => ({ mutate: vi.fn() }),
  useCardTimeline: () => ({ data: undefined, isPending: false, isError: true }),
  useMoveMoney: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useMoveHistory: () => ({ data: [] }),
}))
vi.mock('../../../api/targets', () => ({ useTarget: () => ({ data: null }) }))
vi.mock('../../../api/accounts', () => ({ useAccounts: () => ({ data: state.accounts }) }))
vi.mock('../../../api/liabilities', () => ({ useLiabilities: () => ({ data: [] }) }))
vi.mock('../../../api/categories', () => ({
  useCategories: () => ({ data: state.categories }),
  useCategoryGroups: () => ({ data: [] }),
}))
vi.mock('../TargetEditor', () => ({ TargetEditor: () => null }))
vi.mock('../TransactionsPeekModal/TransactionsPeekModal', () => ({
  TransactionsPeekModal: () => null,
}))
vi.mock('../../../hooks/useMediaQuery', () => ({ useIsMobile: () => false }))
vi.mock('../../../stores/uiStore', () => ({
  useUIStore: (sel: (s: unknown) => unknown) =>
    sel({ creditCardsCollapsed: state.collapsed, toggleCreditCardsCollapsed: vi.fn() }),
}))
// The grid's row is its own component with its own tests; here it is enough
// to see which envelope, with which month's figures, the section hands it.
vi.mock('../CategoryRow/CategoryRow', () => ({
  CategoryRow: ({ category, balance }: { category: Category; balance?: CategoryBalance }) => (
    <div data-testid="section-row">
      {category.name} · {String(balance?.available ?? 'none')}
    </div>
  ),
}))

const visaEnvelope = makeCategory({
  id: 'visa-env',
  name: 'Sapphire Visa',
  linked_account_id: 'acct-visa',
  in_card_section: true,
  is_assignable: false,
  is_categorizable: false,
})
const interest = makeCategory({ id: 'interest', name: 'Interest & fees', in_card_section: true })
const rent = makeCategory({ id: 'rent', name: 'Rent' })

function show({ toCategorize = 0 }: { toCategorize?: number } = {}) {
  month.current = {
    cards: [
      cardStatus({ account_id: 'acct-visa', category_id: 'visa-env', name: 'Sapphire Visa' }),
    ],
    category_balances: [{ category_id: 'interest', available: -15, assigned: 0, activity: -15 }],
  } as unknown as BudgetMonth
  state.accounts = [{ id: 'acct-visa', uncategorized_count: toCategorize }]
  render(<CreditCardsSection budgetId="b1" month="2026-08-01" />)
}

beforeEach(() => {
  state.collapsed = false
  state.categories = [visaEnvelope, interest, rent]
})

describe('Interest & fees in the Credit cards section', () => {
  it('draws the one envelope the server places there that is not a card’s own', () => {
    show()
    const rows = screen.getAllByTestId('section-row')
    expect(rows).toHaveLength(1)
    expect(rows[0]).toHaveTextContent('Interest & fees · -15')
  })

  it('draws it under a renamed name — the placement is served, not the name', () => {
    state.categories = [visaEnvelope, { ...interest, name: 'Card interest' }, rent]
    show()
    expect(screen.getByTestId('section-row')).toHaveTextContent('Card interest')
  })

  it('draws nothing for it when it is archived or missing', () => {
    // The category list leaves archived envelopes out, so an archived
    // Interest & fees simply is not in it.
    state.categories = [visaEnvelope, rent]
    show()
    expect(screen.queryByTestId('section-row')).toBeNull()
  })

  it('folds away with the cards', () => {
    state.collapsed = true
    show()
    expect(screen.queryByTestId('section-row')).toBeNull()
  })

  it('names it where a card has rows to categorize', async () => {
    show({ toCategorize: 2 })
    await userEvent.click(screen.getByRole('button', { name: /Sapphire Visa/ }))
    expect(screen.getByText(/interest and fees go in Interest & fees/)).toBeInTheDocument()
  })
})
