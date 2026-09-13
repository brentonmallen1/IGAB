/**
 * Sharing modal affordances follow the caller's role: owners manage the
 * roster; members only see it and may leave. The backend enforces the rules —
 * this asserts the modal doesn't offer actions that would 403.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { BudgetMember } from '../../api/budgetMembers'

const membersState = vi.hoisted(() => ({ data: [] as BudgetMember[], isLoading: false }))
const meState = vi.hoisted(() => ({ data: { id: 'me', email: 'me@home.local' } }))
const addMember = vi.hoisted(() => vi.fn((_: string) => Promise.resolve({})))

vi.mock('../../api/budgetMembers', () => ({
  useBudgetMembers: () => membersState,
  useAddBudgetMember: () => ({ mutateAsync: addMember, isPending: false }),
  useRemoveBudgetMember: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('../../api/users', () => ({
  useUsers: () => ({
    data: [
      {
        id: 'me',
        email: 'me@home.local',
        display_name: null,
        is_admin: true,
        is_active: true,
        is_env_admin: false,
      },
      {
        id: 'other',
        email: 'other@home.local',
        display_name: 'Other',
        is_admin: false,
        is_active: true,
        is_env_admin: false,
      },
    ],
  }),
}))
vi.mock('../../api/auth', () => ({ useCurrentUser: () => meState }))

import { SharingModal } from './SharingModal'

function setMembers(members: BudgetMember[]) {
  membersState.data = members
}

describe('SharingModal', () => {
  beforeEach(async () => {
    // Every test opens a Dialog; drain the deferred history.back() of the last.
    await new Promise((r) => setTimeout(r, 0))
    await new Promise((r) => setTimeout(r, 0))
    window.history.replaceState(null, '')
    membersState.data = []
    addMember.mockClear()
  })

  it('keeps Share enabled with nobody picked, and asks for someone on submit', async () => {
    setMembers([{ user_id: 'me', email: 'me@home.local', display_name: null, role: 'owner' }])
    render(<SharingModal budgetId="b1" budgetName="House" onClose={vi.fn()} />)
    const share = screen.getByRole('button', { name: 'Share' })
    expect(share).toHaveClass('dialog-btn', 'dialog-btn--primary')
    expect(share).toBeEnabled()
    await userEvent.click(share)
    expect(screen.getByText('Pick someone to share with')).toHaveClass('dialog-form__error')
    expect(addMember).not.toHaveBeenCalled()

    await userEvent.selectOptions(screen.getByLabelText('User to share with'), 'other')
    await userEvent.click(share)
    expect(addMember).toHaveBeenCalledWith('other')
  })

  it('owner sees the share picker and can remove members', () => {
    setMembers([
      { user_id: 'me', email: 'me@home.local', display_name: null, role: 'owner' },
      { user_id: 'p', email: 'p@home.local', display_name: 'Partner', role: 'member' },
    ])
    render(<SharingModal budgetId="b1" budgetName="House" onClose={vi.fn()} />)
    expect(screen.getByLabelText('User to share with')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Remove' })).toBeInTheDocument()
  })

  it('member sees no picker and no remove-others — only Leave', () => {
    setMembers([
      { user_id: 'owner', email: 'o@home.local', display_name: 'Owner', role: 'owner' },
      { user_id: 'me', email: 'me@home.local', display_name: null, role: 'member' },
    ])
    render(<SharingModal budgetId="b1" budgetName="House" onClose={vi.fn()} />)
    expect(screen.queryByLabelText('User to share with')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /leave/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Remove' })).not.toBeInTheDocument()
  })
})
