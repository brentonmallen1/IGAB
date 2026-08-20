/**
 * User administration affordances: the env-managed admin must never be
 * offered a password reset (the API would refuse and boot would revert it),
 * you cannot deactivate yourself, and everyone else gets both actions.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
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

vi.mock('../../../api/users', () => ({
  useUsers: () => ({ data: USERS, isLoading: false }),
  useCreateUser: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateUser: () => ({ mutateAsync: vi.fn(), isPending: false }),
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
