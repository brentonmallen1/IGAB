/**
 * The Activity peek opens on the month whose Activity was clicked.
 *
 * It used to open on the ten most recent rows of all time, so in a past month
 * the figure on the grid and the list under it shared nothing. The window is
 * the whole month — not "so far" — because Activity counts a future-dated row
 * later in the month, and the list behind the number has to show it.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const peek = vi.hoisted(() =>
  vi.fn((..._args: unknown[]) => ({
    data: { transactions: [], total_count: 0 },
    isPending: false,
  }))
)
vi.mock('../../../api/transactions', () => ({
  useTransactionsPeek: peek,
  usePayees: () => ({ data: [] }),
}))
vi.mock('../../../api/accounts', () => ({ useAccounts: () => ({ data: [] }) }))
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }))

import { TransactionsPeekModal } from './TransactionsPeekModal'

beforeEach(() => {
  document.body.innerHTML = ''
  peek.mockClear()
})

const lastCall = () => peek.mock.calls[peek.mock.calls.length - 1]

describe('the Activity peek', () => {
  it('asks for the whole clicked month, every row of it', () => {
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
    const [, , limit, range] = lastCall()
    expect(range).toEqual({ start: '2026-09-01', end: '2026-09-30' })
    expect(limit).toBeGreaterThan(10)
  })

  it('drops the window when asked to load everything', () => {
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
    expect(lastCall()[3]).toEqual({ start: '2026-02-01', end: '2026-02-28' })
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
    const [, , limit, range] = lastCall()
    expect(range).toBeNull()
    expect(limit).toBe(10)
    expect(screen.getByText('Recent transactions')).toBeTruthy()
  })
})
