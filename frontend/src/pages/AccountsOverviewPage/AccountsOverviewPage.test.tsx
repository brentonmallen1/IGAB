/**
 * Closing an account used to be one-way through the UI.
 *
 * The list was fetched with `includeClosed: showClosed`, and the "Show
 * closed" toggle was rendered only when the fetched list contained a closed
 * account — which, with the toggle off, it never could. The one control that
 * could turn it on was hidden behind itself, so a closed account was
 * reachable only by typing its URL.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { AccountsOverviewPage } from './AccountsOverviewPage'
import type { Account } from '../../types'

const updateMutate = vi.hoisted(() => vi.fn(() => Promise.resolve({})))
let accounts: Account[] = []

vi.mock('../../api/accounts', () => ({
  // Faithful to the server: `includeClosed: false` really does omit them.
  // A mock that returned closed accounts either way would have let the bug
  // this file exists for pass unnoticed.
  useAccounts: (_budgetId: string | null, options?: { includeClosed?: boolean }) => ({
    data: options?.includeClosed ? accounts : accounts.filter((a) => !a.is_closed),
  }),
  useDeleteAccount: () => ({ mutateAsync: vi.fn() }),
  useUpdateAccount: () => ({ mutateAsync: updateMutate }),
}))
vi.mock('../../api/liabilities', () => ({ useLiabilities: () => ({ data: [] }) }))
vi.mock('../../api/accountTypes', () => ({ useAccountTypes: () => ({ data: undefined }) }))
vi.mock('../../api/simplefin', () => ({
  useSimpleFINConnections: () => ({ data: [] }),
  useSyncSimpleFIN: () => ({ mutateAsync: vi.fn(), mutate: vi.fn(), isPending: false }),
  useSyncAllSimpleFIN: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSimpleFINRateLimitStatus: () => ({ data: undefined }),
  formatSyncSummary: () => '',
}))
vi.mock('../../components/accounts/AccountHygienePanel', () => ({
  AccountHygienePanel: () => null,
}))
vi.mock('../../components/accounts/AccountTypesPanel', () => ({ AccountTypesPanel: () => null }))
vi.mock('../../hooks/useFormatters', () => ({
  useFormatters: () => ({
    formatMoney: (n: number) => `$${n.toFixed(2)}`,
    formatDate: (d: string) => d,
  }),
}))
vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}))

const confirmAsync = vi.hoisted(() => vi.fn(() => Promise.resolve(true)))
vi.mock('../../stores/confirmStore', () => ({ confirmAsync }))

vi.mock('../../stores/appStore', () => ({
  useAppStore: (sel: (s: { currentBudgetId: string }) => unknown) => sel({ currentBudgetId: 'b1' }),
}))

function account(over: Partial<Account> = {}): Account {
  return {
    id: 'a1',
    name: 'Checking',
    account_type: 'checking',
    classification: 'asset',
    on_budget: true,
    is_closed: false,
    balance: 100.0,
    cleared_balance: 100.0,
    uncleared_balance: 0.0,
    uncategorized_count: 0,
    simplefin_account_id: null,
    last_simplefin_sync_at: null,
    last_reconciled_at: null,
    ...over,
  } as Account
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AccountsOverviewPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  updateMutate.mockClear()
  confirmAsync.mockClear()
  accounts = []
})

describe('AccountsOverviewPage — closed accounts', () => {
  it('offers no toggle when nothing is closed', () => {
    accounts = [account()]
    renderPage()
    expect(screen.queryByText('Show closed')).not.toBeInTheDocument()
  })

  it('offers the toggle as soon as one account is closed, and hides it until asked', async () => {
    accounts = [account(), account({ id: 'a2', name: 'Old Savings', is_closed: true })]
    renderPage()

    expect(screen.queryByText('Old Savings')).not.toBeInTheDocument()
    await userEvent.click(screen.getByText('Show closed'))
    expect(screen.getByText('Old Savings')).toBeInTheDocument()
  })

  it('reopens a closed account from its own row', async () => {
    accounts = [account({ id: 'a2', name: 'Old Savings', is_closed: true })]
    renderPage()
    await userEvent.click(screen.getByText('Show closed'))

    await userEvent.click(screen.getByRole('button', { name: 'Reopen account' }))

    expect(confirmAsync).toHaveBeenCalled()
    expect(updateMutate).toHaveBeenCalledWith({ id: 'a2', is_closed: false })
  })
})
