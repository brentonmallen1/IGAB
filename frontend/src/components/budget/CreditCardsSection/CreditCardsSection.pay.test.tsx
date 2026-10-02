/**
 * Paying a card from the budget page.
 *
 * The opened card offered Transactions, Release, Paydown target, Payoff
 * projection and Breakdown — everything but paying it, which lived only on
 * the card's register toolbar. The payment the strip exists to lead to was
 * two navigations away from the place that says how much to pay.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CreditCardsSection } from './CreditCardsSection'
import type { BudgetMonth } from '../../../types'
import { cardStatus } from '../../../test-utils/cardFixture'

const month: { current: BudgetMonth | undefined } = { current: undefined }
const state = vi.hoisted(() => ({
  accounts: [] as unknown[],
  paid: [] as string[],
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
  useCategories: () => ({ data: [] }),
  useCategoryGroups: () => ({ data: [] }),
}))
vi.mock('../TargetEditor', () => ({ TargetEditor: () => null }))
vi.mock('../TransactionsPeekModal/TransactionsPeekModal', () => ({
  TransactionsPeekModal: () => null,
}))
vi.mock('../../accounts/CardPaymentModal', () => ({
  CardPaymentModal: ({ accountId }: { accountId: string }) => {
    state.paid.push(accountId)
    return <div role="dialog" aria-label="Payment" />
  },
}))
vi.mock('../../../hooks/useMediaQuery', () => ({ useIsMobile: () => false }))
vi.mock('../../../stores/uiStore', () => ({
  useUIStore: (sel: (s: unknown) => unknown) =>
    sel({ creditCardsCollapsed: false, toggleCreditCardsCollapsed: vi.fn() }),
}))

beforeEach(() => {
  state.paid = []
  state.accounts = [
    {
      id: 'acct-visa',
      on_budget: true,
      classification: 'liability',
      account_type: 'credit_card',
      uncategorized_count: 0,
    },
  ]
  month.current = {
    cards: [
      cardStatus({ account_id: 'acct-visa', category_id: 'visa-env', name: 'Sapphire Visa' }),
    ],
    category_balances: [],
  } as unknown as BudgetMonth
})

describe('an opened card', () => {
  it('leads its actions with Make a payment, which opens the payment for that card', async () => {
    render(<CreditCardsSection budgetId="b1" month="2026-08-01" />)
    await userEvent.click(screen.getByRole('button', { name: /Sapphire Visa/ }))
    const pay = screen.getByRole('button', { name: 'Make a payment' })
    expect(pay.parentElement?.firstElementChild).toBe(pay)
    await userEvent.click(pay)
    expect(screen.getByRole('dialog', { name: 'Payment' })).toBeInTheDocument()
    expect(state.paid).toContain('acct-visa')
  })
})
