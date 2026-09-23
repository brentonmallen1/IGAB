/**
 * Release: taking money back out of a card's envelope.
 *
 * Offered on any card holding money, not only one with a surplus. Set aside
 * is committed to a bill, but committing it was a decision and so is taking
 * it back — and past the spare it raises that card's Uncovered dollar for
 * dollar. The app's job is to say so, not to refuse.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CreditCardsSection } from './CreditCardsSection'
import { releaseAnchors } from './cardRow'
import type { BudgetMonth, CardStatus, Category } from '../../../types'

const month: { current: BudgetMonth | undefined } = { current: undefined }
const moveMoney = vi.fn(() => Promise.resolve())

vi.mock('../../../api/budgets', () => ({
  useBudgetMonth: () => ({ data: month.current }),
  useSetAssignment: () => ({ mutate: vi.fn() }),
  useCardTimeline: () => ({ data: undefined, isPending: false, isError: true }),
  useMoveMoney: () => ({ mutateAsync: moveMoney, isPending: false }),
  useMoveHistory: () => ({ data: [] }),
}))
vi.mock('../../../api/targets', () => ({ useTarget: () => ({ data: null }) }))
vi.mock('../../../api/liabilities', () => ({ useLiabilities: () => ({ data: [] }) }))
vi.mock('../TargetEditor', () => ({ TargetEditor: () => null }))
vi.mock('../TransactionsPeekModal/TransactionsPeekModal', () => ({
  TransactionsPeekModal: () => null,
}))
vi.mock('../../../hooks/useMediaQuery', () => ({ useIsMobile: () => true }))

const envelope = { id: 'c1', name: 'Sapphire Visa', is_assignable: true } as Category
vi.mock('../../../api/categories', () => ({
  useCategories: () => ({ data: [{ id: 'c1', name: 'Sapphire Visa', is_assignable: true }] }),
  useCategoryGroups: () => ({ data: [] }),
}))
vi.mock('../../../stores/uiStore', () => ({
  useUIStore: (sel: (s: unknown) => unknown) =>
    sel({ creditCardsCollapsed: false, toggleCreditCardsCollapsed: vi.fn() }),
}))

function card(over: Partial<CardStatus> = {}): CardStatus {
  return {
    account_id: 'a1',
    name: 'Sapphire Visa',
    category_id: 'c1',
    balance: -1500,
    set_aside: 7400,
    uncovered: 0,
    is_closed: false,
    overspent_this_month: 0,
    reserve_discrepancy: 0,
    assigned: 5900,
    reserved: 1500,
    released: 0,
    residual: 0,
    payments: 0,
    riding: 0,
    imported_riding: 0,
    covered: 0,
    opening: 0,
    over_reserved: 5900,
    short_reserved: 0,
    card_credit: 0,
    set_aside_state: 'surplus',
    charged_this_month: 0,
    inflows_this_month: 0,
    paid_this_month: 0,
    debt_change_this_month: 0,
    pending_this_month: 0,
    rode_by_month: [],
    overspent_by_category: [],
    ...over,
  }
}

const money = (n: number) => `$${n.toFixed(2)}`

function show(c: CardStatus) {
  month.current = { cards: [c], category_balances: [] } as unknown as BudgetMonth
  render(<CreditCardsSection budgetId="b1" month="2026-08-01" />)
}

beforeEach(() => {
  moveMoney.mockClear()
})

describe('releaseAnchors', () => {
  it('opens at the spare, not at everything the card is holding', () => {
    // The default offer is the part no debt needs. Taking the whole reserve
    // is allowed and is a different decision.
    expect(releaseAnchors(card(), money).prefill).toBe(5900)
    expect(releaseAnchors(card(), money).ceiling).toBe(7400)
  })

  it('offers the whole reserve on a card with no spare at all', () => {
    // The scoping correction: this is not a surplus tool. A card paying its
    // bill in full has no spare, and needing that cash elsewhere this month
    // is exactly when someone reaches for it.
    const tight = card({
      set_aside: 300,
      balance: -300,
      over_reserved: 0,
      set_aside_state: 'funded',
    })
    expect(releaseAnchors(tight, money).prefill).toBe(300)
  })

  it('states the consequence rather than capping the amount', () => {
    const lines = releaseAnchors(card(), money).lines.join(' ')
    expect(lines).toContain('$5900.00 is spare')
    expect(lines).toMatch(/Uncovered rises/)
    expect(lines).toMatch(/That is allowed/)
  })

  it('does not pretend a card with nothing spare has something spare', () => {
    const tight = card({
      set_aside: 300,
      balance: -300,
      over_reserved: 0,
      set_aside_state: 'funded',
    })
    expect(releaseAnchors(tight, money).lines.join(' ')).toContain('none of it is spare')
  })
})

describe('the Release door', () => {
  it('is there on a card holding money with no surplus', () => {
    show(card({ set_aside: 300, balance: -300, over_reserved: 0, set_aside_state: 'funded' }))
    expect(screen.getByLabelText('Release money from Sapphire Visa')).toBeInTheDocument()
  })

  it('is not offered on a card holding nothing', () => {
    show(card({ set_aside: 0, balance: -300, over_reserved: 0, set_aside_state: 'funded' }))
    expect(screen.queryByLabelText('Release money from Sapphire Visa')).not.toBeInTheDocument()
  })

  it('opens prefilled with the spare, and the amount is editable', async () => {
    show(card())
    await userEvent.click(screen.getByLabelText('Release money from Sapphire Visa'))
    const amount = screen.getByLabelText('Amount') as HTMLInputElement
    expect(amount.value).toBe('5900.00')
    await userEvent.clear(amount)
    await userEvent.type(amount, '7400')
    expect(amount.value).toBe('7400')
  })

  it('says what crossing the spare costs, before anybody crosses it', async () => {
    show(card())
    await userEvent.click(screen.getByLabelText('Release money from Sapphire Visa'))
    expect(screen.getByText(/Uncovered rises by every dollar/)).toBeInTheDocument()
  })

  it('moves money out of the card envelope to Ready to Assign', async () => {
    show(card())
    await userEvent.click(screen.getByLabelText('Release money from Sapphire Visa'))
    await userEvent.click(screen.getByRole('button', { name: 'Move Money' }))
    expect(moveMoney).toHaveBeenCalledWith({
      from_category_id: envelope.id,
      to_category_id: null,
      amount: 5900,
      month: '2026-08-01',
    })
  })
})
