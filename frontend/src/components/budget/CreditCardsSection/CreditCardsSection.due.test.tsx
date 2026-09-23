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
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { BudgetMonth, CardStatus } from '../../../types'
import type { Liability } from '../../../api/liabilities'
import { useUIStore } from '../../../stores/uiStore'

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
    imported_riding: 0,
    covered: 0,
    residual_from_ledgers: 0,
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
  useUIStore.setState({ creditCardsCollapsed: false })
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

describe('the header, which is all a collapsed strip has', () => {
  it('names the card when one bill is close', () => {
    show()

    expect(screen.getByText('Sapphire Visa due in 4 days')).toBeInTheDocument()
  })

  it('still says so with the strip collapsed', () => {
    // The whole point: the rows are gone, and the header is what is left.
    useUIStore.setState({ creditCardsCollapsed: true })
    show()

    expect(screen.queryByRole('table', { name: 'Credit cards' })).not.toBeInTheDocument()
    expect(screen.getByText('Sapphire Visa due in 4 days')).toBeInTheDocument()
  })

  it('counts them and leads with the soonest when several are close', () => {
    month.current = {
      cards: [card(), card({ account_id: 'a2', name: 'Thistledown Card', category_id: 'c2' })],
      category_balances: [],
    } as unknown as BudgetMonth
    rows.liabilities = [due(), due({ id: 'l2', linked_account_id: 'a2', payment_due_day: 15 })]
    show()

    // The 15th is two days out, the 17th four.
    expect(screen.getByText('2 bills due, soonest in 2 days')).toBeInTheDocument()
  })

  it('says nothing when no bill is close', () => {
    vi.setSystemTime(new Date(2026, 8, 1, 12, 0, 0))
    show()

    expect(screen.queryByText(/bills? due|due in|due today/)).not.toBeInTheDocument()
  })

  it('says nothing about a card that owes nothing', () => {
    month.current = {
      cards: [card({ balance: 0, set_aside: 0, reserved: 0 })],
      category_balances: [],
    } as unknown as BudgetMonth
    show()

    expect(screen.queryByText(/due in/)).not.toBeInTheDocument()
  })
})

describe('folding the section', () => {
  // fireEvent, not userEvent: this file pins the clock, and userEvent's own
  // waits run on timers that never advance — every one of these sat until the
  // test timed out. What is under test is a plain onClick, which fireEvent
  // dispatches synchronously.

  it('folds from anywhere in the band, not just the caret', () => {
    // A header that reads as one object should behave as one: aiming at a
    // 13px chevron is a needless ask.
    show()
    expect(screen.getByRole('table', { name: 'Credit cards' })).toBeInTheDocument()

    fireEvent.click(screen.getByText('Sapphire Visa due in 4 days'))

    expect(screen.queryByRole('table', { name: 'Credit cards' })).not.toBeInTheDocument()
  })

  it('folds from the count too', () => {
    show()
    fireEvent.click(screen.getByText(/^1 card/))

    expect(screen.queryByRole('table', { name: 'Credit cards' })).not.toBeInTheDocument()
  })

  it('still folds from the button, exactly once', () => {
    // The button carries no handler of its own — its click bubbles to the
    // band. Two handlers would toggle twice and leave the section open.
    show()
    fireEvent.click(screen.getByRole('button', { name: /Credit cards/ }))

    expect(screen.queryByRole('table', { name: 'Credit cards' })).not.toBeInTheDocument()
  })

  it('opens the explainer without folding the section', () => {
    // The one thing in the band that is not the fold control.
    show()
    fireEvent.click(screen.getByRole('button', { name: 'How credit cards work here' }))

    expect(screen.getByText('How credit cards work here')).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Credit cards' })).toBeInTheDocument()
  })
})
