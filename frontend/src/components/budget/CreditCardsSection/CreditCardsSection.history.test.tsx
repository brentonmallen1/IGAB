/**
 * "Month by month" — the reserve's history, read at a glance.
 *
 * The server walks forward from the first month anything moved and caps
 * nothing, so a long-held card ships years of rows. What that asks of the
 * table is covered here: the recent months first, a bounded well, stripes that
 * actually paint, a year said once, and the month's legs reachable by a tap
 * instead of a `title` tooltip no touch screen can show.
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import type { BudgetMonth, CardStatus } from '../../../types'

const month = vi.hoisted(() => ({ current: {} as Partial<BudgetMonth> }))
const timeline = vi.hoisted(() => ({ current: null as unknown }))

vi.mock('../../../api/budgets', () => ({
  useBudgetMonth: () => ({ data: month.current }),
  useSetAssignment: () => ({ mutate: vi.fn(), isPending: false }),
  useCardTimeline: () => ({ data: timeline.current, isPending: false, isError: false }),
}))
vi.mock('../../../api/targets', () => ({ useTarget: () => ({ data: null }) }))
vi.mock('../../../api/liabilities', () => ({ useLiabilities: () => ({ data: [] }) }))
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
    opening: 0,
    over_reserved: 55,
    short_reserved: 0,
    card_credit: 0,
    charged_this_month: 0,
    inflows_this_month: 0,
    paid_this_month: 0,
    debt_change_this_month: 0,
    pending_this_month: 0,
    rode_by_month: [],
    ...over,
  }
}

function tlMonth(m: string, over: Record<string, number> = {}) {
  return {
    month: m,
    assigned: 0,
    reserved: 0,
    released: 0,
    residual: 0,
    payments: 0,
    reserve_delta: 0,
    set_aside: 0,
    balance: 0,
    riding: 0,
    opening: 0,
    uncovered: 0,
    over_reserved: 0,
    short_reserved: 0,
    card_credit: 0,
    ...over,
  }
}

/** The server's order: oldest first. */
const MONTHS = [
  tlMonth('2025-11-01', { assigned: 200, reserve_delta: 200, set_aside: 200, balance: -50 }),
  tlMonth('2025-12-01', { reserved: 80, reserve_delta: 80, set_aside: 280, balance: -130 }),
  tlMonth('2026-01-01', { payments: 150, reserve_delta: -150, set_aside: 130, balance: 20 }),
  tlMonth('2026-02-01', { released: 15, reserve_delta: -15, set_aside: 115, balance: -60 }),
]

beforeEach(() => {
  month.current = { cards: [card()], category_balances: [] } as unknown as BudgetMonth
  timeline.current = {
    account_id: 'a1',
    name: 'Sapphire Visa',
    months: MONTHS,
    breach: null,
    anchor_month: null,
  }
})

async function openHistory() {
  render(<CreditCardsSection budgetId="b1" month="2026-02-01" />)
  await userEvent.click(screen.getByLabelText('What makes up Ready to pay for Sapphire Visa'))
  await userEvent.click(screen.getByRole('button', { name: /month by month/i }))
}

const dataRows = () => [...document.querySelectorAll('.credit-cards__history-row')].slice(1)

describe('the month-by-month history', () => {
  it('puts the newest month first — the one you opened this to look at', async () => {
    await openHistory()
    const labels = dataRows().map((r) => r.querySelector('button')?.textContent)
    expect(labels).toEqual(['February 2026', 'January 2026', 'December 2025', 'November 2025'])
  })

  it('scrolls in a bounded well rather than growing the drawer', async () => {
    await openHistory()
    // .scroll-list carries the cap and the flex-shrink guard; the component
    // only tunes --scroll-list-max.
    expect(document.querySelector('.credit-cards__history-scroll')!.className).toContain(
      'scroll-list'
    )
  })

  it('stripes every other data row, counting data rows only', async () => {
    await openHistory()
    const striped = dataRows().map((r) => r.className.includes('--alt'))
    // The sticky header and the year separators must not shift the count.
    expect(striped).toEqual([false, true, false, true])
  })

  it('names each year once, as the reader scrolls back into it', async () => {
    await openHistory()
    const years = [...document.querySelectorAll('.credit-cards__history-year')].map(
      (n) => n.textContent
    )
    expect(years).toEqual(['2026', '2025'])
  })

  it('a month opens into its legs — what the title tooltip used to hide', async () => {
    await openHistory()
    // January: a 150 payment and nothing else.
    await userEvent.click(screen.getByRole('button', { name: /january 2026/i }))
    const detail = document.querySelector('.credit-cards__history-detail')!
    expect(within(detail as HTMLElement).getByText('Paid to the card')).toBeInTheDocument()
    expect(detail.textContent).toContain('150.00')
  })

  it('lists only the legs that moved', async () => {
    await openHistory()
    await userEvent.click(screen.getByRole('button', { name: /january 2026/i }))
    const detail = document.querySelector('.credit-cards__history-detail')!
    expect(within(detail as HTMLElement).queryByText('Assigned to this card')).toBeNull()
    expect(within(detail as HTMLElement).queryByText('Released by refunds')).toBeNull()
  })

  it('keeps one month open at a time, so the table stays a table', async () => {
    await openHistory()
    await userEvent.click(screen.getByRole('button', { name: /january 2026/i }))
    await userEvent.click(screen.getByRole('button', { name: /december 2025/i }))
    const details = document.querySelectorAll('.credit-cards__history-detail')
    expect(details).toHaveLength(1)
    expect(details[0].textContent).toContain('Set aside by funded spending')
  })

  it('a second tap closes the month again', async () => {
    await openHistory()
    const jan = screen.getByRole('button', { name: /january 2026/i })
    await userEvent.click(jan)
    expect(jan).toHaveAttribute('aria-expanded', 'true')
    await userEvent.click(jan)
    expect(jan).toHaveAttribute('aria-expanded', 'false')
    expect(document.querySelector('.credit-cards__history-detail')).toBeNull()
  })

  it('says so for a month where nothing moved, rather than showing an empty box', async () => {
    timeline.current = {
      account_id: 'a1',
      name: 'Sapphire Visa',
      months: [tlMonth('2026-02-01', { set_aside: 115, balance: -60 })],
      breach: null,
    }
    await openHistory()
    await userEvent.click(screen.getByRole('button', { name: /february 2026/i }))
    expect(screen.getByText(/Nothing moved through the reserve/)).toBeInTheDocument()
  })

  it('carries no title tooltip — it is unreachable on a touch screen', async () => {
    await openHistory()
    for (const row of dataRows()) expect(row.getAttribute('title')).toBeNull()
  })

  it('marks the month the reserve first went below zero', async () => {
    timeline.current = {
      account_id: 'a1',
      name: 'Sapphire Visa',
      months: MONTHS,
      breach: {
        month: '2026-01-01',
        set_aside_before: 280,
        set_aside_after: -20,
        legs: [{ leg: 'payments', amount: 300 }],
      },
    }
    await openHistory()
    expect(screen.getByText(/first went below zero in January 2026/)).toBeInTheDocument()
    const marked = dataRows().filter((r) => r.className.includes('--breach'))
    expect(marked).toHaveLength(1)
    expect(marked[0].textContent).toContain('January 2026')
  })
})

describe('the import-anchor seam', () => {
  it('labels where the history ends, after the oldest month', async () => {
    timeline.current = {
      account_id: 'a1',
      name: 'Sapphire Visa',
      // Oldest entry is B−1: the opening leg, per the server's contract.
      months: [
        tlMonth('2025-11-01', { opening: 200, reserve_delta: 200, set_aside: 200 }),
        ...MONTHS.slice(1),
      ],
      breach: null,
      anchor_month: '2025-12-01',
    }
    await openHistory()
    expect(screen.getByText(/Imported from YNAB/)).toBeInTheDocument()
    expect(screen.getByText(/earlier months live in the register and reports/)).toBeInTheDocument()
    // Below the oldest data row — scrolling down walks backwards in time.
    const rows = [...document.querySelectorAll('[role="row"]')]
    expect(rows[rows.length - 1].textContent).toMatch(/Imported from YNAB/)
  })

  it('does not disturb the striping — like the year separators', async () => {
    timeline.current = {
      account_id: 'a1',
      name: 'Sapphire Visa',
      months: MONTHS,
      breach: null,
      anchor_month: '2025-11-01',
    }
    await openHistory()
    const striped = dataRows().filter((r) => r.className.includes('--alt'))
    expect(striped).toHaveLength(2)
  })

  it('is absent on an unanchored budget', async () => {
    await openHistory()
    expect(screen.queryByText(/Imported from YNAB/)).not.toBeInTheDocument()
  })
})
