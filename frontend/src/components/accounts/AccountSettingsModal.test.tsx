/**
 * An existing Other Asset can be re-marked as a savings vehicle from its own
 * settings. The New Account form was the only place the toggle was tested, and
 * an account created before the flag existed — a brokerage imported as Other
 * Asset — can only be corrected here.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AccountSettingsModal } from './AccountSettingsModal'
import { useAppStore } from '../../stores/appStore'
import type { Account } from '../../types'

const updateMutate = vi.hoisted(() => vi.fn((_: unknown) => Promise.resolve({})))
const account = vi.hoisted(() => ({
  current: {} as Partial<Account>,
}))

vi.mock('../../api/accounts', () => ({
  useAccounts: () => ({ data: [account.current] }),
  useUpdateAccount: () => ({ mutateAsync: updateMutate, isPending: false }),
  useScanDuplicates: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('../../api/simplefin', () => {
  const idle = () => ({ mutateAsync: vi.fn(), isPending: false })
  return {
    useSimpleFINConnections: () => ({ data: [] }),
    useSimpleFINRemoteAccounts: () => ({ data: [], isFetching: false }),
    useSimpleFINConfig: () => ({ data: undefined }),
    useLinkSimpleFINAccount: idle,
    useUnlinkSimpleFINAccount: idle,
    useUpdateAccountSimpleFINSettings: idle,
  }
})
// No registry yet: the form falls back to the built-in mirror.
vi.mock('../../api/accountTypes', () => ({
  useAccountTypes: () => ({ data: undefined }),
}))

const toggle = () => screen.queryByLabelText('Counts as savings') as HTMLInputElement | null

beforeEach(async () => {
  // Every test opens the Dialog; drain the deferred history.back() of the last.
  await new Promise((r) => setTimeout(r, 0))
  await new Promise((r) => setTimeout(r, 0))
  window.history.replaceState(null, '')
  updateMutate.mockClear()
  useAppStore.setState({ currentBudgetId: 'b1' })
  account.current = {
    id: 'car',
    name: 'Second Car',
    account_type: 'other_asset',
    classification: 'asset',
    on_budget: false,
    counts_as_savings: false,
    is_closed: false,
    note: null,
    budget_start_date: null,
  }
})

describe('AccountSettingsModal counts-as-savings toggle', () => {
  it('shows an Other Asset its stored choice', () => {
    render(<AccountSettingsModal accountId="car" onClose={vi.fn()} />)
    expect(toggle()?.checked).toBe(false)
  })

  it('saves an Other Asset re-marked as savings', async () => {
    render(<AccountSettingsModal accountId="car" onClose={vi.fn()} />)
    await userEvent.click(toggle()!)
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(updateMutate).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'car', account_type: 'other_asset', counts_as_savings: true })
    )
  })

  it('is not offered once the account is on budget', () => {
    account.current = { ...account.current, on_budget: true }
    render(<AccountSettingsModal accountId="car" onClose={vi.fn()} />)
    expect(toggle()).toBeNull()
  })
})
