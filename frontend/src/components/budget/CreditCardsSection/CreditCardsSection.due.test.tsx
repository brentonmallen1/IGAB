/**
 * The bill reminder on the card strip.
 *
 * It reads `reminderForCard` (utils/paymentDue.ts) — the same wiring as the
 * app-wide banner — so the two cannot disagree about a bill. It speaks while
 * the card owes something and a bill is close and unpaid ("Due in 4 days"),
 * or went by unpaid ("Past due", in red, with a red dot on the line and the
 * section header). It goes once a payment lands after the last due date.
 * The strip is not dismissible: dismissing only quiets the banner.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { BudgetMonth, CardStatus } from '../../../types'
import type { Liability } from '../../../api/liabilities'
import { useUIStore } from '../../../stores/uiStore'

const month = vi.hoisted(() => ({ current: {} as Partial<BudgetMonth> }))
const rows = vi.hoisted(() => ({ liabilities: [] as Partial<Liability>[] }))

interface AccountRow {
  id: string
  uncategorized_count: number
  on_budget: boolean
  classification: 'liability'
  budget_start_date: string | null
  created_at: string
}
const accounts = vi.hoisted(() => ({ current: [] as AccountRow[] }))

/** An on-budget card, in the budget since January. */
function account(id: string, over: Partial<AccountRow> = {}): AccountRow {
  return {
    id,
    uncategorized_count: 0,
    on_budget: true,
    classification: 'liability',
    budget_start_date: null,
    created_at: '2026-01-05T15:00:00Z',
    ...over,
  }
}
vi.mock('../../../api/budgets', () => ({
  useBudgetMonth: () => ({ data: month.current }),
  useSetAssignment: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock('../../../api/targets', () => ({ useTarget: () => ({ data: null }) }))
vi.mock('../../../api/accounts', () => ({ useAccounts: () => ({ data: accounts.current }) }))
vi.mock('../../../api/liabilities', () => ({ useLiabilities: () => ({ data: rows.liabilities }) }))
vi.mock('../../../api/categories', () => ({ useCategories: () => ({ data: [] }) }))
vi.mock('../TargetEditor', () => ({ TargetEditor: () => null }))
vi.mock('../TransactionsPeekModal/TransactionsPeekModal', () => ({
  TransactionsPeekModal: () => null,
}))

import { CreditCardsSection } from './CreditCardsSection'
import { cardStatus } from '../../../test-utils/cardFixture'

/** Only the fields this row reads — the rest of a Liability is a payoff
 *  projection the strip never touches. Due on the 17th, owing $1,240, watched
 *  from 1 Aug and paid 10 Aug: August's bill was paid, September's is not. */
function due(over: Partial<Liability> = {}): Partial<Liability> {
  return {
    id: 'l1',
    linked_account_id: 'a1',
    current_balance: 1240,
    recent_payment_dates: ['2026-08-10'],
    payment_window_start: '2026-08-01',
    payment_due_kind: 'day_of_month',
    payment_due_day: 17,
    payment_due_cycle_days: null,
    payment_due_anchor: null,
    ...over,
  }
}

function card(over: Partial<CardStatus> = {}): CardStatus {
  return cardStatus({ balance: -1240, set_aside: 1240, reserved: 1240, ...over })
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
  accounts.current = [account('a1'), account('a2')]
})

afterEach(() => {
  vi.useRealTimers()
})

describe('the bill-due chip', () => {
  it('says how far off the bill is on a card that owes something', () => {
    show()

    expect(screen.getByText('Due in 4 days')).toBeInTheDocument()
  })

  it('says today on the due date itself', () => {
    vi.setSystemTime(new Date(2026, 8, 17, 12, 0, 0))
    show()

    expect(screen.getByText('Due today')).toBeInTheDocument()
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
        // 3 Sep itself was paid on the 1st.
        payment_window_start: '2026-09-01',
        recent_payment_dates: ['2026-09-01'],
      }),
    ]
    show('2026-10-01')

    expect(screen.getByText('Due in 3 days')).toBeInTheDocument()
  })

  it('stays on when the only payment since was a late one for the bill before', () => {
    // 17 Aug was paid on the 20th — late. That payment is spent on August,
    // so September's bill is still due; it used to read as paid.
    rows.liabilities = [due({ recent_payment_dates: ['2026-08-20'] })]
    show()

    expect(screen.getByText('Due in 4 days')).toBeInTheDocument()
  })

  it('goes once a payment lands after the last due date', () => {
    rows.liabilities = [due({ recent_payment_dates: ['2026-08-10', '2026-09-05'] })]
    show()

    expect(screen.queryByText(/^Due /)).not.toBeInTheDocument()
  })

  it('stays quiet while the bill is still far off', () => {
    vi.setSystemTime(new Date(2026, 8, 1, 12, 0, 0))
    show()

    expect(screen.queryByText(/^Due /)).not.toBeInTheDocument()
  })

  it('stays quiet on a card that owes nothing', () => {
    rows.liabilities = [due({ current_balance: 0 })]
    month.current = {
      cards: [card({ balance: 0, set_aside: 0, reserved: 0 })],
      category_balances: [],
    } as unknown as BudgetMonth
    show()

    expect(screen.queryByText(/^Due /)).not.toBeInTheDocument()
  })

  it('stays quiet on a card holding a credit balance', () => {
    // The liability's `current_balance` is owed-POSITIVE, so a credit is
    // negative there — the sign the reminder reads.
    rows.liabilities = [due({ current_balance: -75 })]
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
    // A reminder is a fact about NOW and the strip is the ledger through the
    // month being viewed. Pairing them on a past month would put a live
    // "due in 4 days" beside figures from a year ago.
    show('2025-11-01')

    expect(screen.queryByText(/^Due /)).not.toBeInTheDocument()
  })
})

describe('a bill past due', () => {
  // Due on the 3rd; 1 Aug paid the 3 Aug bill, and 3 Sep went by unpaid.
  beforeEach(() => {
    rows.liabilities = [due({ payment_due_day: 3, recent_payment_dates: ['2026-08-01'] })]
  })

  it('says so on the chip, in red, and never offers to dismiss it here', () => {
    show()

    const chip = screen.getByText('Past due')
    expect(chip).toHaveClass('credit-cards__due--past-due')
    expect(screen.queryByRole('button', { name: /dismiss/i })).not.toBeInTheDocument()
  })

  it('puts the red dot on the line and the section header', () => {
    show()

    expect(screen.getByRole('img', { name: 'A card bill is past due' })).toBeInTheDocument()
    expect(
      document.querySelector('.credit-cards__line .credit-cards__mark--past-due')
    ).not.toBeNull()
  })

  it('names the date in the header, which is all a collapsed strip has', () => {
    useUIStore.setState({ creditCardsCollapsed: true })
    show()

    expect(screen.getByText('Sapphire Visa past due since Sep 3')).toBeInTheDocument()
  })

  it('keeps the line word on where the money stands', () => {
    // The chip carries the bill; the word is still the card's position.
    show()

    expect(screen.getByText('covered')).toBeInTheDocument()
  })

  it('clears once a late payment lands', () => {
    rows.liabilities = [
      due({ payment_due_day: 3, recent_payment_dates: ['2026-08-01', '2026-09-08'] }),
    ]
    show()

    expect(screen.queryByText('Past due')).not.toBeInTheDocument()
    expect(screen.queryByRole('img', { name: 'A card bill is past due' })).not.toBeInTheDocument()
  })

  it('is not claimed for a due date before the card joined the budget', () => {
    accounts.current = [account('a1', { budget_start_date: '2026-09-10' })]
    show()

    expect(screen.queryByText('Past due')).not.toBeInTheDocument()
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

    expect(screen.queryByRole('list', { name: 'Credit cards' })).not.toBeInTheDocument()
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
    rows.liabilities = [due({ current_balance: 0 })]
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
    expect(screen.getByRole('list', { name: 'Credit cards' })).toBeInTheDocument()

    fireEvent.click(screen.getByText('Sapphire Visa due in 4 days'))

    expect(screen.queryByRole('list', { name: 'Credit cards' })).not.toBeInTheDocument()
  })

  it('folds from the count too', () => {
    show()
    fireEvent.click(screen.getByText(/^1 card/))

    expect(screen.queryByRole('list', { name: 'Credit cards' })).not.toBeInTheDocument()
  })

  it('still folds from the button, exactly once', () => {
    // The button carries no handler of its own — its click bubbles to the
    // band. Two handlers would toggle twice and leave the section open.
    show()
    fireEvent.click(screen.getByRole('button', { name: /Credit cards/ }))

    expect(screen.queryByRole('list', { name: 'Credit cards' })).not.toBeInTheDocument()
  })

  it('holds nothing but the fold control', () => {
    // The "How credit cards work here" essay lived behind a button here; each
    // card now explains itself in place, so the band is one control.
    show()
    expect(screen.queryByRole('button', { name: /how credit cards work/i })).toBeNull()
    expect(screen.getByRole('list', { name: 'Credit cards' })).toBeInTheDocument()
  })
})
