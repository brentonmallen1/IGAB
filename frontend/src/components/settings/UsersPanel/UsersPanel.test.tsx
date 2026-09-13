/**
 * User administration affordances: the env-managed admin must never be
 * offered a password reset (the API would refuse and boot would revert it),
 * you cannot deactivate yourself, and everyone else gets both actions.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ManagedUser } from '../../../api/users'

const USERS: ManagedUser[] = [
  {
    id: 'u-admin',
    email: 'admin@home.local',
    display_name: 'Admin',
    is_admin: true,
    is_active: true,
    is_env_admin: true,
  },
  {
    id: 'u-partner',
    email: 'partner@home.local',
    display_name: 'Partner',
    is_admin: false,
    is_active: true,
    is_env_admin: false,
  },
  {
    id: 'u-old',
    email: 'old@home.local',
    display_name: null,
    is_admin: false,
    is_active: false,
    is_env_admin: false,
  },
]

const updateUser = vi.hoisted(() => vi.fn((_: unknown) => Promise.resolve({})))
vi.mock('../../../api/users', () => ({
  useUsers: () => ({ data: USERS, isLoading: false }),
  useCreateUser: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateUser: () => ({ mutateAsync: updateUser, isPending: false }),
}))
vi.mock('../../../api/auth', () => ({
  useCurrentUser: () => ({ data: USERS[0] }),
}))

import { UsersPanel } from './UsersPanel'

describe('UsersPanel', () => {
  it('shows the env note instead of a reset button for the bootstrap admin', () => {
    render(<UsersPanel />)
    expect(screen.getByText('managed by ADMIN_PASSWORD')).toBeInTheDocument()
    // Exactly two reset buttons: partner + deactivated user, never the admin
    expect(screen.getAllByRole('button', { name: /reset .*password/i })).toHaveLength(2)
  })

  it('never offers deactivation of the signed-in user', () => {
    render(<UsersPanel />)
    const deactivate = screen.getAllByRole('button', { name: /deactivate|reactivate/i })
    // admin (me) gets none; partner gets Deactivate; old gets Reactivate
    expect(deactivate).toHaveLength(2)
  })

  it('marks deactivated accounts', () => {
    render(<UsersPanel />)
    expect(screen.getByText('deactivated')).toBeInTheDocument()
  })
})

/**
 * Set password was disabled until eight characters were typed, with nothing
 * saying why. It is enabled now and answers a short password in the footer.
 */
describe('UsersPanel reset-password dialog', () => {
  beforeEach(async () => {
    await new Promise((r) => setTimeout(r, 0))
    await new Promise((r) => setTimeout(r, 0))
    window.history.replaceState(null, '')
    updateUser.mockClear()
  })

  async function openReset() {
    render(<UsersPanel />)
    await userEvent.click(screen.getAllByRole('button', { name: /reset .*password/i })[0])
  }

  it('is a shared dialog form with a labelled password field', async () => {
    await openReset()
    const input = screen.getByLabelText('New password')
    expect(input.closest('form')).toHaveClass('dialog-form')
    expect(input.closest('label')).toHaveClass('dialog-form__field')
    expect(screen.getByRole('button', { name: 'Set password' })).toHaveClass(
      'dialog-btn',
      'dialog-btn--primary'
    )
  })

  it('keeps Set password enabled and refuses a short password on submit', async () => {
    await openReset()
    await userEvent.type(screen.getByLabelText('New password'), 'short')
    const submit = screen.getByRole('button', { name: 'Set password' })
    expect(submit).toBeEnabled()
    await userEvent.click(submit)
    expect(screen.getByText('Use at least 8 characters')).toHaveClass('dialog-form__error')
    expect(updateUser).not.toHaveBeenCalled()
  })

  it('sets a long-enough password', async () => {
    await openReset()
    await userEvent.type(screen.getByLabelText('New password'), 'longenough')
    await userEvent.click(screen.getByRole('button', { name: 'Set password' }))
    expect(updateUser).toHaveBeenCalledWith({ id: 'u-partner', password: 'longenough' })
  })
})
