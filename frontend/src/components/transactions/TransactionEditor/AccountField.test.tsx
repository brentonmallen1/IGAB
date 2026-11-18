/**
 * The editor's account picker draws its groups — Recent, Budget accounts,
 * Tracking — under the house group headers. It was a native <select>, whose
 * <optgroup> labels are the browser's, unthemed and unsearchable.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { Account } from '../../../types'

const media = vi.hoisted(() => ({ mobile: false }))
vi.mock('../../../hooks/useMediaQuery', () => ({
  useMediaQuery: () => media.mobile,
  useIsMobile: () => media.mobile,
}))

import { AccountField } from './AccountField'

const account = (id: string, name: string, on_budget = true, is_closed = false) =>
  ({ id, name, on_budget, is_closed }) as Account

const CHECKING = account('a1', 'Harborstone Checking')
const CARD = account('a2', 'Sapphire Visa')
const BROKERAGE = account('a3', 'Cascade Point Brokerage', false)

function renderField(props: Partial<Parameters<typeof AccountField>[0]> = {}) {
  const onChange = vi.fn()
  render(
    <AccountField
      accounts={[CHECKING, CARD, BROKERAGE]}
      recent={[CARD]}
      value={null}
      onChange={onChange}
      current={null}
      lockReason={null}
      note={null}
      {...props}
    />
  )
  return { onChange }
}

const headers = () =>
  Array.from(document.querySelectorAll('.combobox__group-header')).map((h) => h.textContent)

describe('AccountField', () => {
  it('renders Recent, Budget accounts and Tracking group headers', () => {
    renderField()
    fireEvent.focus(screen.getByRole('combobox', { name: 'Account' }))
    expect(headers()).toEqual(['Recent', 'Budget accounts', 'Tracking'])
    const listbox = screen.getByRole('listbox')
    expect(within(listbox).getAllByRole('option', { name: 'Sapphire Visa' })).toHaveLength(2)
    expect(within(listbox).getByRole('option', { name: 'Cascade Point Brokerage' })).toBeTruthy()
  })

  it('picks an account by id', () => {
    const { onChange } = renderField()
    const input = screen.getByRole('combobox', { name: 'Account' })
    fireEvent.focus(input)
    fireEvent.change(input, { target: { value: 'Brok' } })
    fireEvent.mouseDown(screen.getByRole('option', { name: 'Cascade Point Brokerage' }))
    expect(onChange).toHaveBeenCalledWith('a3')
  })

  it('reads the closed account a row already sits in, so a save cannot re-file it', () => {
    const closed = account('a9', 'Old Savings', true, true)
    renderField({ value: 'a9', current: closed })
    expect(screen.getByRole('combobox', { name: 'Account' })).toHaveValue('Old Savings (closed)')
  })

  it('reads the account and its lock reason when it cannot move', () => {
    renderField({ value: 'a1', current: CHECKING, lockReason: 'The bank feed decides' })
    expect(screen.queryByRole('combobox', { name: 'Account' })).toBeNull()
    expect(screen.getByLabelText('Account: Harborstone Checking')).toBeTruthy()
    expect(screen.getByText('The bank feed decides')).toBeTruthy()
  })

  it('on a phone, opens a sheet with the same groups', () => {
    media.mobile = true
    try {
      renderField()
      fireEvent.click(screen.getByRole('button', { name: 'Account' }))
      const labels = Array.from(document.querySelectorAll('.selection-sheet__group-label')).map(
        (l) => l.textContent
      )
      expect(labels).toEqual(['Recent', 'Budget accounts', 'Tracking'])
    } finally {
      media.mobile = false
    }
  })
})
