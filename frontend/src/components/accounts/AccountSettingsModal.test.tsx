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
    useRefetchSimpleFINAccount: idle,
    useUpdateAccountSimpleFINSettings: idle,
    formatSyncSummary: () => '',
  }
})
// The modal asks whether this account's bank link still resolves, so it can
// offer a one-click relink. Nothing is broken in these fixtures.
vi.mock('../../api/syncLogs', () => ({
  useSyncHealth: () => ({
    data: {
      orphaned_links: [],
      needs_auth: [],
      balance_drift: [],
      unserved: [],
      last_run_at: null,
    },
  }),
}))
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
    counts_toward_emergency_fund: false,
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

describe('AccountSettingsModal emergency-fund mark', () => {
  const mark = () =>
    screen.queryByRole('checkbox', { name: 'Counts toward emergency fund' }) as HTMLInputElement

  beforeEach(() => {
    account.current = {
      ...account.current,
      id: 'reserve',
      name: 'Harborstone Reserve',
      account_type: 'savings',
      counts_as_savings: true,
      counts_toward_emergency_fund: true,
    }
  })

  it('shows the stored mark and saves it', async () => {
    render(<AccountSettingsModal accountId="reserve" onClose={vi.fn()} />)
    expect(mark().checked).toBe(true)
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(updateMutate).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'reserve', counts_toward_emergency_fund: true })
    )
  })

  it('clears it when Counts as savings is turned off', async () => {
    render(<AccountSettingsModal accountId="reserve" onClose={vi.fn()} />)
    await userEvent.click(toggle()!)
    expect(mark()).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(updateMutate).toHaveBeenCalledWith(
      expect.objectContaining({ counts_as_savings: false, counts_toward_emergency_fund: false })
    )
  })
})

/**
 * The account-numbers editor sits inside the settings form. It used to be a
 * <form> of its own: the parser drops a nested form, so its Enter and its
 * "Save numbers" submitted the settings form — name, type, note and all.
 */
describe('AccountSettingsModal account numbers', () => {
  const openEditor = async () => {
    render(<AccountSettingsModal accountId="car" onClose={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Add routing / account number…' }))
  }
  // The settings save carries the name; the numbers save carries only numbers.
  const settingsSaves = () =>
    updateMutate.mock.calls.filter(([arg]) => 'name' in (arg as object)).length
  const numberSaves = () =>
    updateMutate.mock.calls.filter(([arg]) => 'account_number' in (arg as object))

  it('renders no form inside another form', async () => {
    await openEditor()
    expect(document.querySelectorAll('form form')).toHaveLength(0)
    expect(document.querySelectorAll('form')).toHaveLength(1)
  })

  it('saves the numbers without submitting the settings', async () => {
    await openEditor()
    await userEvent.type(screen.getByLabelText('Account number'), '12345678')
    await userEvent.click(screen.getByRole('button', { name: 'Save numbers' }))
    expect(numberSaves()).toEqual([
      [{ id: 'car', account_number: '12345678', routing_number: null }],
    ])
    expect(settingsSaves()).toBe(0)
  })

  it('saves the numbers on Enter without submitting the settings', async () => {
    await openEditor()
    await userEvent.type(screen.getByLabelText('Routing number'), '123456789{Enter}')
    expect(numberSaves()).toHaveLength(1)
    expect(settingsSaves()).toBe(0)
  })

  it('saves the settings without saving the half-typed numbers', async () => {
    await openEditor()
    await userEvent.type(screen.getByLabelText('Account number'), '12345678')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(settingsSaves()).toBe(1)
    expect(numberSaves()).toHaveLength(0)
  })
})
