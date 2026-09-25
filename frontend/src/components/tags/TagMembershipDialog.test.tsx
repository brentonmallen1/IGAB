/**
 * "Categories tagged {name}": the checklist from the tag's side sends one diff.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { TagMembership } from '../../api/tags'

const state = vi.hoisted(() => ({
  membership: null as TagMembership | null,
  mutateAsync: vi.fn(),
}))

vi.mock('../../api/tags', () => ({
  useTagMembership: () => ({ data: state.membership, isLoading: false, isError: false }),
  useSetTagMembership: () => ({ mutateAsync: state.mutateAsync, isPending: false }),
}))

import { makeMembershipRow as row } from '../../test-utils/factories'
import { TagMembershipDialog } from './TagMembershipDialog'

function membership(savingsTag: boolean, name = 'Emergency fund'): TagMembership {
  return {
    tag: {
      id: 't1',
      name,
      system_key: savingsTag ? 'emergency_fund' : null,
      savings_tag: savingsTag,
    },
    categories: [
      row({
        id: 'fund',
        name: 'Emergency Fund',
        group_id: 'g-goals',
        group_name: 'Goals',
        member: true,
        savings_role: 'kept_here',
      }),
      row({
        id: 'old',
        name: 'Old Buffer',
        group_id: 'g-goals',
        group_name: 'Goals',
        is_archived: true,
      }),
      row({ id: 'groceries', name: 'Groceries' }),
    ],
  }
}

function show(onClose = vi.fn()) {
  render(
    <TagMembershipDialog budgetId="b1" tagId="t1" tagName="Emergency fund" onClose={onClose} />
  )
  return onClose
}

beforeEach(async () => {
  await new Promise((r) => setTimeout(r, 0))
  await new Promise((r) => setTimeout(r, 0))
  window.history.replaceState(null, '')
  state.mutateAsync.mockReset()
  state.mutateAsync.mockResolvedValue({})
  state.membership = membership(true)
})

describe('TagMembershipDialog', () => {
  it('titles itself by the tag and lists categories under their groups', () => {
    show()
    expect(screen.getByText('Categories tagged Emergency fund')).toBeInTheDocument()
    const list = screen.getByRole('group', { name: 'Categories tagged Emergency fund' })
    expect(within(list).getByText('Goals')).toBeInTheDocument()
    expect(within(list).getByRole('checkbox', { name: /Emergency Fund/ })).toBeChecked()
    expect(within(list).getByRole('checkbox', { name: /Groceries/ })).not.toBeChecked()
    expect(within(list).getByText('archived')).toBeInTheDocument()
  })

  it('filters by category or group name', () => {
    show()
    fireEvent.change(screen.getByLabelText('Filter'), { target: { value: 'groc' } })
    expect(screen.queryByRole('checkbox', { name: /Emergency Fund/ })).not.toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /Groceries/ })).toBeInTheDocument()
  })

  it('shows the mode control only on checked rows of a savings tag, naming the served default', () => {
    show()
    const mode = screen.getByRole('combobox', {
      name: 'Emergency Fund counts as saved',
    })
    expect(within(mode).getByRole('option', { name: 'in budget (default)' })).toBeInTheDocument()
    expect(
      screen.queryByRole('combobox', { name: 'Groceries counts as saved' })
    ).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('checkbox', { name: /Groceries/ }))
    const added = screen.getByRole('combobox', { name: 'Groceries counts as saved' })
    // Being added: its default is the server's to say, so none is named.
    expect(within(added).getByRole('option', { name: 'default' })).toBeInTheDocument()
  })

  it('has no mode control for a tag that is not a savings tag', () => {
    state.membership = membership(false, 'Essential')
    show()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })

  it('Save sends the diff — adds, removes and changed modes — then closes', async () => {
    const onClose = show()
    fireEvent.click(screen.getByRole('checkbox', { name: /Groceries/ }))
    fireEvent.change(screen.getByRole('combobox', { name: 'Groceries counts as saved' }), {
      target: { value: 'sent_out' },
    })
    fireEvent.click(screen.getByRole('checkbox', { name: /Emergency Fund/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(state.mutateAsync).toHaveBeenCalledTimes(1))
    expect(state.mutateAsync.mock.calls[0][0]).toEqual({
      add: ['groceries'],
      remove: ['fund'],
      savings_modes: { groceries: 'sent_out' },
    })
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('an unchanged Save closes without writing anything', async () => {
    const onClose = show()
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(state.mutateAsync).not.toHaveBeenCalled()
  })

  it('keeps the archived note beside a listed archived row', () => {
    show()
    const old = screen.getByRole('checkbox', { name: /Old Buffer/ })
    expect(old).toHaveAccessibleName(/archived/)
    expect(old).not.toBeDisabled()
  })

  it('Save never names a row counted through another tag', async () => {
    state.membership = {
      tag: { id: 't1', name: 'Cost of living', system_key: 'cost_of_living', savings_tag: false },
      categories: [
        row({ id: 'rent', name: 'Rent', group_name: 'Bills', implied_by: 'Essential' }),
        row({
          id: 'water',
          name: 'Water',
          group_name: 'Bills',
          member: true,
          implied_by: 'Essential',
        }),
        row({ id: 'gym', name: 'Gym', group_name: 'Bills', member: true }),
      ],
    }
    const onClose = show()
    const rent = screen.getByRole('checkbox', { name: /Rent.*counted through Essential/ })
    expect(rent).toBeChecked()
    expect(rent).toBeDisabled()
    // A disabled box fires nothing; the diff skips it regardless.
    fireEvent.click(rent)
    fireEvent.click(screen.getByRole('checkbox', { name: /Gym/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(state.mutateAsync).toHaveBeenCalledTimes(1))
    expect(state.mutateAsync.mock.calls[0][0]).toEqual({
      add: [],
      remove: ['gym'],
      savings_modes: {},
    })
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('says why a refused save failed and stays open', async () => {
    state.mutateAsync.mockRejectedValue(new Error('nope'))
    const onClose = show()
    fireEvent.click(screen.getByRole('checkbox', { name: /Groceries/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/Could not save/)
    expect(onClose).not.toHaveBeenCalled()
  })
})
