/**
 * The Activity peek opens on the month whose Activity was clicked.
 *
 * It used to open on the ten most recent rows of all time, so in a past month
 * the figure on the grid and the list under it shared nothing. Then it asked
 * for a calendar window — but Activity counts a row in its BUDGET month
 * (`txn_filters.BUDGET_MONTH`), and a late arrival dated in the import month
 * counts in the month after. So the window listed that row under the month
 * whose figure never counted it, and left it out of the month whose figure
 * did. It asks for the budget month now; the server pins the late-arrival
 * case (`test_budget_month_listing.py`).
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const peek = vi.hoisted(() =>
  vi.fn((..._args: unknown[]) => ({
    data: { transactions: [] as unknown[], total_count: 0, total_amount: 0 },
    isPending: false,
  }))
)
vi.mock('../../../api/transactions', () => ({
  useTransactionsPeek: peek,
  usePayees: () => ({ data: [] }),
}))
vi.mock('../../../api/accounts', () => ({ useAccounts: () => ({ data: [] }) }))
vi.mock('../../../api/categories', () => ({
  useCategories: () => ({ data: [{ id: 'c-groc', name: 'Groceries' }] }),
}))
vi.mock('./CardReserveSummary', () => ({
  CardReserveSummary: ({ listedNet }: { listedNet: number }) => (
    <div data-testid="reserve-summary">{listedNet}</div>
  ),
}))
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }))

import { TransactionsPeekModal } from './TransactionsPeekModal'

beforeEach(() => {
  document.body.innerHTML = ''
  peek.mockClear()
})

const lastCall = () => peek.mock.calls[peek.mock.calls.length - 1]

describe('the Activity peek', () => {
  it('asks for the clicked budget month, every row of it', () => {
    render(
      <TransactionsPeekModal
        budgetId="b1"
        scope={{
          kind: 'category',
          categoryId: 'c1',
          categoryName: 'Groceries',
          month: '2026-09-01',
        }}
        onClose={vi.fn()}
      />
    )
    const [, scope, limit, budgetMonth] = lastCall()
    expect(scope).toEqual({ categoryId: 'c1', accountId: null })
    // The budget month, not 1–30 Sep: a late arrival dated 28 Aug on an
    // anchored budget counts here, and the list has to hold it.
    expect(budgetMonth).toBe('2026-09-01')
    expect(limit).toBeGreaterThan(10)
  })

  it('drops the month when asked to load everything', () => {
    render(
      <TransactionsPeekModal
        budgetId="b1"
        scope={{
          kind: 'category',
          categoryId: 'c1',
          categoryName: 'Groceries',
          month: '2026-02-01',
        }}
        onClose={vi.fn()}
      />
    )
    expect(lastCall()[3]).toBe('2026-02-01')
    fireEvent.click(screen.getByRole('button', { name: 'Load all transactions' }))
    expect(lastCall()[3]).toBeNull()
    expect(screen.getByText('All transactions')).toBeTruthy()
  })

  it('keeps the recent list where no month was given (an account’s whole ledger)', () => {
    render(
      <TransactionsPeekModal
        budgetId="b1"
        scope={{ kind: 'account', accountId: 'a1', accountName: 'Sapphire Visa' }}
        onClose={vi.fn()}
      />
    )
    const [, , limit, budgetMonth] = lastCall()
    expect(budgetMonth).toBeNull()
    expect(limit).toBe(10)
    expect(screen.getByText('Recent transactions')).toBeTruthy()
  })
})

describe('what set a card’s money aside', () => {
  const SCOPE = {
    kind: 'card-reserve',
    accountId: 'visa',
    accountName: 'Sapphire Visa',
    month: '2026-09-01',
  } as const

  it('asks for the card rows envelopes claim, in the budget month', () => {
    render(<TransactionsPeekModal budgetId="b1" scope={SCOPE} onClose={vi.fn()} />)
    const [, scope, , budgetMonth] = lastCall()
    expect(scope).toEqual({ accountId: 'visa', cardReserving: true })
    expect(budgetMonth).toBe('2026-09-01')
    expect(screen.getByText('What set money aside in September 2026')).toBeTruthy()
    // A month's figure: there is no "all" for it to widen to.
    expect(screen.queryByRole('button', { name: 'Load all transactions' })).toBeNull()
  })

  it('names each row’s envelope, and closes the list with the lines to Set aside', () => {
    peek.mockReturnValue({
      data: {
        transactions: [
          {
            id: 't1',
            date: '2026-09-04',
            amount: -82.5,
            account_id: 'visa',
            category_id: 'c-groc',
            payee_id: null,
            memo: null,
            import_description: 'Corner Market',
          },
        ],
        total_count: 1,
        total_amount: -82.5,
      },
      isPending: false,
    })
    render(<TransactionsPeekModal budgetId="b1" scope={SCOPE} onClose={vi.fn()} />)

    expect(screen.getByRole('columnheader', { name: 'Category' })).toBeTruthy()
    expect(screen.getByRole('cell', { name: 'Groceries' })).toBeTruthy()
    // The summary is handed the served total, never a sum of the rows.
    expect(screen.getByTestId('reserve-summary').textContent).toBe('-82.5')
  })
})
