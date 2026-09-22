/**
 * The bill-due indicator on the card strip.
 *
 * It fires on two facts together — the bill is close, and the card still owes
 * something — and on nothing else. A due date on a settled card is a calendar
 * fact nobody needs interrupting them, and a balance with no due date on file
 * has nothing to be close to.
 *
 * What it must never do is imply a bill was missed. The app cannot see whether
 * a statement was paid, so the date it shows is always today or later and the
 * copy never says "late" or "overdue".
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { BudgetMonth, CardStatus } from '../../../types'
import type { Liability } from '../../../api/liabilities'

const month = vi.hoisted(() => ({ current: {} as Partial<BudgetMonth> }))
const rows = vi.hoisted(() => ({ liabilities: [] as Partial<Liability>[] }))

vi.mock('../../../api/budgets', () => ({
  useBudgetMonth: () => ({ data: month.current }),
  useSetAssignment: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock('../../../api/targets', () => ({ useTarget: () => ({ data: null }) }))
vi.mock('../../../api/liabilities', () => ({ useLiabilities: () => ({ data: rows.liabilities }) }))
vi.mock('../../../api/categories', () => ({ useCategories: () => ({ data: [] }) }))
vi.mock('../TargetEditor', () => ({ TargetEditor: () => null }))
vi.mock('../TransactionsPeekModal/TransactionsPeekModal', () => ({
  TransactionsPeekModal: () => null,
}))

import { CreditCardsSection } from './CreditCardsSection'

/** Only the fields this row reads — the rest of a Liability is a payoff
 *  projection the strip never touches. */
function due(over: Partial<Liability> = {}): Partial<Liability> {
  return {
    id: 'l1',
    linked_account_id: 'a1',
    payment_due_kind: 'day_of_month',
    payment_due_day: 17,
    payment_due_cycle_days: null,
    payment_due_anchor: null,
    ...over,
  }
}

function card(over: Partial<CardStatus> = {}): CardStatus {
  return {
    account_id: 'a1',
    name: 'Sapphire Visa',
    category_id: 'c1',
    balance: -1240,
    set_aside: 1240,
    uncovered: 0,
    is_closed: false,
    overspent_this_month: 0,
    reserve_discrepancy: 0,
    assigned: 0,
    reserved: 1240,
    released: 0,
    residual: 0,
    payments: 0,
    riding: 0,
    opening: 0,
    over_reserved: 0,
    short_reserved: 0,
    card_credit: 0,
    set_aside_state: 'funded',
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

function show(viewedMonth = '2026-09-01') {
  render(
    <MemoryRouter>
      <CreditCardsSection budgetId="b1" month={viewedMonth} />
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date(2026, 8, 13, 12, 0, 0)) // Sunday 13 Sep 2026
  month.current = { cards: [card()], category_balances: [] } as unknown as BudgetMonth
  rows.liabilities = [due()]
})

afterEach(() => {
  vi.useRealTimers()
})

describe('the bill-due chip', () => {
  it('says how far off the bill is on a card that owes something', () => {
    show()

    expect(screen.getByText('Due in 4 days')).toBeInTheDocument()
  })

  it('says today on the due date itself, and never that it is late', () => {
    vi.setSystemTime(new Date(2026, 8, 17, 12, 0, 0))
    show()

    expect(screen.getByText('Due today')).toBeInTheDocument()
    expect(screen.queryByText(/overdue|late/i)).not.toBeInTheDocument()
  })

  it('counts a cycle from its anchor rather than from a day of the month', () => {
    // 3 Sep + 31 days = 4 Oct; on 1 Oct that is three days away. The
    // day-of-month spelling cannot express this card at all.
    vi.setSystemTime(new Date(2026, 9, 1, 12, 0, 0))
    month.current = { cards: [card()], category_balances: [] } as unknown as BudgetMonth
    rows.liabilities = [
      due({
        payment_due_kind: 'cycle_days',
        payment_due_day: null,
        payment_due_cycle_days: 31,
        payment_due_anchor: '2026-09-03',
      }),
    ]
    show('2026-10-01')

    expect(screen.getByText('Due in 3 days')).toBeInTheDocument()
  })

  it('stays quiet while the bill is still far off', () => {
    vi.setSystemTime(new Date(2026, 8, 1, 12, 0, 0))
    show()

    expect(screen.queryByText(/^Due /)).not.toBeInTheDocument()
  })

  it('stays quiet on a card that owes nothing', () => {
    month.current = {
      cards: [card({ balance: 0, set_aside: 0, reserved: 0 })],
      category_balances: [],
    } as unknown as BudgetMonth
    show()

    expect(screen.queryByText(/^Due /)).not.toBeInTheDocument()
  })

  it('stays quiet on a card holding a credit balance', () => {
    // `balance` is owed-negative, so a positive one is the card holding money.
    // Converting the sign the wrong way round at the call site would light
    // this chip up on exactly the cards with nothing to pay.
    month.current = {
      cards: [
        card({ balance: 75, set_aside: 0, card_credit: 75, set_aside_state: 'card_holds_it' }),
      ],
      category_balances: [],
    } as unknown as BudgetMonth
    show()

    expect(screen.queryByText(/^Due /)).not.toBeInTheDocument()
  })

  it('stays quiet on a card with no due date on file', () => {
    rows.liabilities = [due({ payment_due_day: null })]
    show()

    expect(screen.queryByText(/^Due /)).not.toBeInTheDocument()
  })

  it('stays quiet on a card with no liability row at all', () => {
    rows.liabilities = []
    show()

    expect(screen.queryByText(/^Due /)).not.toBeInTheDocument()
  })

  it('stays out of a month in the past', () => {
    // The due date is a fact about NOW and `balance` is the ledger through
    // the month being viewed. Pairing them on a past month would put a live
    // "due in 4 days" beside a balance from a year ago.
    show('2025-11-01')

    expect(screen.queryByText(/^Due /)).not.toBeInTheDocument()
  })
})
