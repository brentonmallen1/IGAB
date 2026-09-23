/**
 * "Set aside" opens into the five flows it is a running total of.
 *
 * A card's reserve is `assigned + reserved − released − residual − payments`,
 * and the surface used to show only the total — so every question this model
 * raised (the refused repayment, the unreleased reservation, the assignment
 * that never left) needed a developer to answer.
 *
 * The panel renders served figures and must never sum them into a reserve of
 * its own: a client-side second opinion about what a set-aside is made of is
 * the exact shape of the defect that put the panel here.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import type { BudgetMonth, CardStatus } from '../../../types'

const month = vi.hoisted(() => ({ current: {} as Partial<BudgetMonth> }))

vi.mock('../../../api/budgets', () => ({
  useBudgetMonth: () => ({ data: month.current }),
  useSetAssignment: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock('../../../api/targets', () => ({ useTarget: () => ({ data: null }) }))
// No liability rows: the payoff link stays out, so this file keeps testing the
// breakdown rather than needing a router around it.
vi.mock('../../../api/liabilities', () => ({ useLiabilities: () => ({ data: [] }) }))
vi.mock('../../../api/categories', () => ({ useCategories: () => ({ data: [] }) }))
vi.mock('../TargetEditor', () => ({ TargetEditor: () => null }))
vi.mock('../TransactionsPeekModal/TransactionsPeekModal', () => ({
  TransactionsPeekModal: () => null,
}))

import { CreditCardsSection } from './CreditCardsSection'

function card(over: Partial<CardStatus> = {}): CardStatus {
  return {
    account_id: 'a1',
    name: 'Sapphire Visa',
    category_id: 'c1',
    balance: -60,
    set_aside: 115,
    uncovered: 0,
    is_closed: false,
    overspent_this_month: 0,
    reserve_discrepancy: 0,
    assigned: 40,
    reserved: 100,
    released: 20,
    residual: 0,
    payments: 5,
    riding: 0,
    imported_riding: 0,
    covered: 0,
    residual_from_ledgers: 0,
    paid_ahead_unmirrored: 0,
    ride_reaches_this_card: true,
    opening: 0,
    // Kept coherent with balance/set_aside above rather than zeroed: 115
    // reserved against 60 owed IS over-reserved by 55, and a fixture that
    // said otherwise would let the row contradict itself unnoticed.
    over_reserved: 55,
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

beforeEach(() => {
  month.current = { cards: [card()], category_balances: [] } as unknown as BudgetMonth
})

/** The breakdown's own total row. "Set aside" is also a column header, so
 *  the label alone is ambiguous. */
function totalRow() {
  return document.querySelector('.credit-cards__leg--total')
}

describe('the Set aside breakdown', () => {
  it('stays closed until asked', () => {
    render(<CreditCardsSection budgetId="b1" month="2026-08-01" />)
    expect(screen.queryByText('Assigned to this card')).toBeNull()
  })

  it('names each leg that moved and the total they reach', async () => {
    render(<CreditCardsSection budgetId="b1" month="2026-08-01" />)
    await userEvent.click(screen.getByLabelText('What makes up Set aside for Sapphire Visa'))

    expect(screen.getByText('Assigned to this card')).toBeInTheDocument()
    expect(screen.getByText('Set aside by funded spending')).toBeInTheDocument()
    expect(screen.getByText('Released by refunds')).toBeInTheDocument()
    expect(screen.getByText('Paid to the card')).toBeInTheDocument()
    // The legs reach a total, labelled the same as the column they explain.
    expect(totalRow()?.textContent).toContain('115')
  })

  it('leaves a leg out when it never moved', async () => {
    render(<CreditCardsSection budgetId="b1" month="2026-08-01" />)
    await userEvent.click(screen.getByLabelText('What makes up Set aside for Sapphire Visa'))
    expect(screen.queryByText('Refunds beyond what was reserved')).toBeNull()
  })

  it('says riding debt sits outside the total, because it does', async () => {
    month.current = {
      cards: [card({ riding: 30, uncovered: 30 })],
      category_balances: [],
    } as unknown as BudgetMonth
    render(<CreditCardsSection budgetId="b1" month="2026-08-01" />)
    await userEvent.click(screen.getByLabelText('What makes up Set aside for Sapphire Visa'))
    expect(screen.getByText(/rode onto this card when a month ended short/)).toBeInTheDocument()
    expect(screen.getByText(/sits outside the total above/)).toBeInTheDocument()
  })

  it('names the months that rode, and back-funding before assigning', async () => {
    // The old note offered only "assign to the card" — the expensive remedy.
    // Funding the month that ended short retires the ride outright, because
    // the walk is recomputed from scratch on every request, and nothing said
    // so. The month is the actionable half, so the panel has to name it.
    month.current = {
      cards: [
        card({
          riding: 30,
          uncovered: 30,
          rode_by_month: [
            { month: '2026-07-01', amount: 20 },
            { month: '2026-06-01', amount: 10 },
          ],
        }),
      ],
      category_balances: [],
    } as unknown as BudgetMonth
    render(<CreditCardsSection budgetId="b1" month="2026-08-01" />)
    await userEvent.click(screen.getByLabelText('What makes up Set aside for Sapphire Visa'))
    expect(screen.getByText(/Fund an envelope in the month it ended short/)).toBeInTheDocument()
    expect(screen.getByText(/assign to the card instead/)).toBeInTheDocument()
    // Largest first: that is the month worth back-funding before the others.
    const listed = document.querySelectorAll('.credit-cards__ride-months li span:first-child')
    expect([...listed].map((n) => n.textContent)).toEqual(['July 2026', 'June 2026'])
  })

  it('does not call imported debt spending from a month that ended short', async () => {
    // A YNAB import: the card arrives owing 2,000 nobody had set aside for.
    // That used to share `riding` with the budget's own rides, so the block
    // said "$2,000.00 of spending rode onto this card when a month ended
    // short" and offered to fix it by funding a month that never existed.
    month.current = {
      cards: [card({ riding: 0, imported_riding: 2000, uncovered: 2000, set_aside: 0 })],
      category_balances: [],
    } as unknown as BudgetMonth
    render(<CreditCardsSection budgetId="b1" month="2026-08-01" />)
    await userEvent.click(screen.getByLabelText('What makes up Set aside for Sapphire Visa'))
    expect(
      screen.getByText(/came in with the budget as debt nothing was set aside for/)
    ).toBeInTheDocument()
    expect(screen.queryByText(/rode onto this card when a month ended short/)).toBeNull()
    // The envelope remedy is not offered: nothing it could reach.
    expect(screen.queryByText(/Fund an envelope in the month it ended short/)).toBeNull()
    expect(screen.getByText(/assigning to the card is what retires it/)).toBeInTheDocument()
  })

  it('tells the two kinds of ride apart when a card carries both', async () => {
    month.current = {
      cards: [card({ riding: 60, imported_riding: 400, uncovered: 460, set_aside: 0 })],
      category_balances: [],
    } as unknown as BudgetMonth
    render(<CreditCardsSection budgetId="b1" month="2026-08-01" />)
    await userEvent.click(screen.getByLabelText('What makes up Set aside for Sapphire Visa'))
    expect(screen.getByText(/\$60\.00 of spending rode onto this card/)).toBeInTheDocument()
    expect(screen.getByText(/\$400\.00 came in with the budget/)).toBeInTheDocument()
    // Both remedies, each beside the debt it can actually reach.
    expect(screen.getByText(/Fund an envelope in the month it ended short/)).toBeInTheDocument()
  })

  it('shows the month the debt moved, separately from the lifetime legs', async () => {
    month.current = {
      cards: [card({ charged_this_month: 412, paid_this_month: 640, debt_change_this_month: 228 })],
      category_balances: [],
    } as unknown as BudgetMonth
    render(<CreditCardsSection budgetId="b1" month="2026-08-01" />)
    await userEvent.click(screen.getByLabelText('What makes up Set aside for Sapphire Visa'))
    expect(screen.getByText('This month')).toBeInTheDocument()
    expect(screen.getByText('Debt decreased')).toBeInTheDocument()
  })

  it('puts the reconciling credit in the list, so the month adds up on its face', async () => {
    // The shape a card produced, invented and rescaled: charged 2,400, paid
    // nothing, debt down 1,500 — three figures that cannot be reconciled
    // without the fourth. The 3,900 that explains them was prose under the
    // list, so the panel showed arithmetic that visibly did not work.
    month.current = {
      cards: [
        card({
          charged_this_month: 2400,
          inflows_this_month: 3900,
          paid_this_month: 0,
          debt_change_this_month: 1500,
        }),
      ],
      category_balances: [],
    } as unknown as BudgetMonth
    render(<CreditCardsSection budgetId="b1" month="2026-08-01" />)
    await userEvent.click(screen.getByLabelText('What makes up Set aside for Sapphire Visa'))

    const rows = [...document.querySelectorAll('.credit-cards__legs-month .credit-cards__leg')]
    const labelled = (label: string) =>
      rows.find((r) => r.querySelector('dt')?.textContent?.startsWith(label))

    // Every term that moved the balance is a row, all served, and they
    // reconcile: 3,900 received − 2,400 charged = 1,500 down. The received
    // figure comes from the server; the sub-rows are its split, and with no
    // paired payment the whole of it is "other credits".
    expect(labelled('Charged')?.querySelector('dd')?.textContent).toContain('2,400.00')
    expect(labelled('Received on the card')?.querySelector('dd')?.textContent).toContain('3,900.00')
    expect(labelled('of which: Other credits')?.querySelector('dd')?.textContent).toContain(
      '3,900.00'
    )
    expect(labelled('of which: Paid from your accounts')).toBeUndefined()
    expect(labelled('Debt decreased')?.querySelector('dd')?.textContent).toContain('1,500.00')

    // The explanation stays a footnote; the amount does not live there.
    const note = document.querySelector('.credit-cards__legs-note')
    expect(note?.textContent).toContain('never linked')
    expect(note?.textContent).not.toContain('3,900.00')
  })

  it('draws the month block when a credit is the only thing that moved', async () => {
    // charged 0 and paid 0 used to hide the block entirely, so a card whose
    // debt moved purely on a refund showed a note explaining a list nobody saw.
    month.current = {
      cards: [
        card({
          charged_this_month: 0,
          inflows_this_month: 90,
          paid_this_month: 0,
          debt_change_this_month: 90,
        }),
      ],
      category_balances: [],
    } as unknown as BudgetMonth
    render(<CreditCardsSection budgetId="b1" month="2026-08-01" />)
    await userEvent.click(screen.getByLabelText('What makes up Set aside for Sapphire Visa'))
    expect(screen.getByText('This month')).toBeInTheDocument()
    expect(screen.getByText(/Other credits/)).toBeInTheDocument()
  })

  it('renders the served total rather than a sum of its own', async () => {
    // The legs deliberately do NOT add up here. The panel must show what the
    // server said, not 40 + 100 - 20 - 0 - 5.
    month.current = {
      cards: [card({ set_aside: 999 })],
      category_balances: [],
    } as unknown as BudgetMonth
    render(<CreditCardsSection budgetId="b1" month="2026-08-01" />)
    await userEvent.click(screen.getByLabelText('What makes up Set aside for Sapphire Visa'))
    expect(totalRow()?.textContent).toContain('999')
    expect(totalRow()?.textContent).not.toContain('115')
  })
})

/** The decision lives in cardRow.ts and is tested there. These pin that the
 *  row actually draws it — a correct decision rendered nowhere is the same
 *  defect from the user's side. */
describe('what the row says about a reserve', () => {
  it('does not call a card overpaid while it still owes money', async () => {
    // The screenshot: -220 reserved against a card owing 5,400, with the whole
    // balance uncovered one column to the right. Rescaled and invented.
    month.current = {
      cards: [
        card({
          balance: -5400,
          set_aside: -220,
          uncovered: 5400,
          short_reserved: 220,
          over_reserved: 0,
          payments: 220,
          set_aside_state: 'paid_ahead',
        }),
      ],
      category_balances: [],
    } as unknown as BudgetMonth
    render(<CreditCardsSection budgetId="b1" month="2026-08-01" />)
    expect(screen.queryByText(/overpaid/i)).not.toBeInTheDocument()
    // The column prints $0.00 and the distance is beside it, on the row. The
    // reason is one tap away — see CreditCardsSection.why.test.tsx.
    expect(screen.getByText('$220.00 below zero')).toBeInTheDocument()
  })

  it('keeps the word for the one state it is true of', async () => {
    month.current = {
      cards: [
        card({
          balance: 50,
          set_aside: -50,
          uncovered: 0,
          short_reserved: 50,
          card_credit: 50,
          over_reserved: 0,
          set_aside_state: 'card_holds_it',
        }),
      ],
      category_balances: [],
    } as unknown as BudgetMonth
    render(<CreditCardsSection budgetId="b1" month="2026-08-01" />)
    expect(screen.getByText('credit balance')).toBeInTheDocument()
  })

  it('reports an over-reserve the discrepancy check is silent about', async () => {
    // reserve_discrepancy is 0 by design here — T1 excuses an over-reserve
    // explained by assignments — so a row keyed on it would say nothing.
    month.current = {
      cards: [
        card({
          balance: -1500,
          set_aside: 7400,
          over_reserved: 5900,
          assigned: 5900,
          reserve_discrepancy: 0,
          set_aside_state: 'surplus',
        }),
      ],
      category_balances: [],
    } as unknown as BudgetMonth
    render(<CreditCardsSection budgetId="b1" month="2026-08-01" />)
    expect(screen.getByText(/spare$/)).toBeInTheDocument()
    expect(screen.queryByText(/does not add up/)).not.toBeInTheDocument()
  })

  it('shows $0.00 and explains itself without anybody hovering anything', async () => {
    // F2, the root cause. `reserveNote().title`, `debtMovement().title` and
    // the drift warning were `title` attributes, and on the installed iOS PWA
    // a tooltip cannot be reached at all — the row read "-$100.00 ahead of
    // budget" with no way to learn more. getByText, never
    // toHaveAttribute('title'): if this passes through a tooltip again, it
    // fails. The explanation moved behind a button since — a button an iOS
    // PWA can tap, which a tooltip still is not.
    month.current = {
      cards: [
        card({
          balance: -1900,
          set_aside: -100,
          uncovered: 1900,
          short_reserved: 100,
          residual: 500,
          reserve_discrepancy: 12,
          set_aside_state: 'refund_outran_envelope',
        }),
      ],
      category_balances: [],
    } as unknown as BudgetMonth
    render(<CreditCardsSection budgetId="b1" month="2026-08-01" />)

    expect(screen.queryByText('-$100.00')).not.toBeInTheDocument()
    expect(screen.getByTitle(/Transactions on/)).toHaveTextContent('$0.00')
    expect(screen.getByText('$100.00 below zero')).toBeInTheDocument()

    await userEvent.click(
      screen.getByRole('button', { name: 'What is happening with Sapphire Visa' })
    )
    // Names the $500 that came back, not the $100 left of it.
    expect(screen.getByText(/\$500\.00 came back onto this card/)).toBeInTheDocument()
    expect(screen.getByText(/\$12\.00 of this Set aside is not explained/)).toBeInTheDocument()

    for (const el of document.querySelectorAll('[title]')) {
      expect(el.getAttribute('title')).not.toMatch(/came back|below zero|not explained/)
    }
  })

  it('shows the debt moving, framed as debt rather than as the balance', async () => {
    month.current = {
      cards: [card({ debt_change_this_month: 228, charged_this_month: 412, paid_this_month: 640 })],
      category_balances: [],
    } as unknown as BudgetMonth
    render(<CreditCardsSection budgetId="b1" month="2026-08-01" />)
    expect(screen.getByText(/^debt decreased /)).toBeInTheDocument()
  })
})
