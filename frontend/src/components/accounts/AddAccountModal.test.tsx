/**
 * Counts as savings is offered only where the server reads it — an off-budget
 * asset — and a type change resets it to that type's default, the same way
 * On Budget resets. An Other Asset arrives off, so a car someone adds is not
 * counted as savings unless they say so.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AddAccountModal } from './AddAccountModal'
import { useAppStore } from '../../stores/appStore'

const createMutate = vi.hoisted(() => vi.fn((_: unknown) => Promise.resolve({})))
vi.mock('../../api/accounts', () => ({
  useCreateAccount: () => ({ mutateAsync: createMutate, isPending: false }),
}))
// No registry yet: the form falls back to the built-in mirror.
vi.mock('../../api/accountTypes', () => ({
  useAccountTypes: () => ({ data: undefined }),
}))

const toggle = () => screen.queryByLabelText('Counts as savings') as HTMLInputElement | null
const typeSelect = () => screen.getByRole('combobox') as HTMLSelectElement

beforeEach(async () => {
  // Every test opens the Dialog; drain the deferred history.back() of the last.
  await new Promise((r) => setTimeout(r, 0))
  await new Promise((r) => setTimeout(r, 0))
  window.history.replaceState(null, '')
  createMutate.mockClear()
  useAppStore.setState({ currentBudgetId: 'b1' })
})

describe('AddAccountModal counts-as-savings toggle', () => {
  it('is not offered on an on-budget account', () => {
    render(<AddAccountModal onClose={vi.fn()} />)
    expect(toggle()).toBeNull()
  })

  it('is not offered on an off-budget liability', async () => {
    render(<AddAccountModal onClose={vi.fn()} />)
    await userEvent.selectOptions(typeSelect(), 'loan')
    expect(toggle()).toBeNull()
  })

  it('arrives off for an Other Asset and on for an Investment', async () => {
    render(<AddAccountModal onClose={vi.fn()} />)
    await userEvent.selectOptions(typeSelect(), 'other_asset')
    expect(toggle()?.checked).toBe(false)
    await userEvent.selectOptions(typeSelect(), 'investment')
    expect(toggle()?.checked).toBe(true)
  })

  it('disappears when the asset is put on budget', async () => {
    render(<AddAccountModal onClose={vi.fn()} initialTypeKey="investment" />)
    expect(toggle()).not.toBeNull()
    await userEvent.click(screen.getByRole('checkbox', { name: 'On budget' }))
    expect(toggle()).toBeNull()
  })

  it('sends the choice with the new account', async () => {
    render(<AddAccountModal onClose={vi.fn()} initialTypeKey="other_asset" />)
    await userEvent.type(screen.getByPlaceholderText('e.g. Chase Checking'), 'Second Car')
    await userEvent.click(screen.getByRole('button', { name: 'Create Account' }))
    expect(createMutate).toHaveBeenCalledWith(
      expect.objectContaining({ account_type: 'other_asset', counts_as_savings: false })
    )
  })
})

describe('AddAccountModal submit', () => {
  // Create Account was disabled until a name was typed, so it drew at half
  // opacity beside the valued-asset form's Save: one primary button, two
  // colours. Every dialog-form primary stays enabled and says what is missing.
  it('stays enabled with no name and asks for one on submit', async () => {
    render(<AddAccountModal onClose={vi.fn()} />)
    const create = screen.getByRole('button', { name: 'Create Account' })
    expect(create).toBeEnabled()
    await userEvent.click(create)
    expect(screen.getByText('Give the account a name')).toBeInTheDocument()
    expect(createMutate).not.toHaveBeenCalled()
  })
})
