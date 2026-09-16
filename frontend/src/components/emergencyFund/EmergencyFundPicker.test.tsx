/**
 * The emergency fund picker: envelopes, accounts and kept elsewhere, saved as
 * one PUT.
 */
import { fireEvent, render as rtlRender, screen, waitFor, within } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { EmergencyFundPicker as PickerData } from '../../api/emergencyFund'
import {
  EMERGENCY_FUND_TAG,
  FUND_MEMBERSHIP,
  FUND_PICKER,
} from '../../test-utils/emergencyFundFixtures'

const state = vi.hoisted(() => ({
  picker: null as unknown,
  save: vi.fn(),
  dismiss: vi.fn(),
}))

vi.mock('../../api/emergencyFund', () => ({
  useEmergencyFund: () => ({ data: state.picker, isError: false }),
  useSetEmergencyFund: () => ({ mutateAsync: state.save, isPending: false }),
}))
vi.mock('../../api/tags', async () => {
  const f = await import('../../test-utils/emergencyFundFixtures')
  return {
    useTags: () => ({ data: [f.EMERGENCY_FUND_TAG] }),
    useTagMembership: (_b: string, tagId: string | null) => ({
      data: tagId === f.EMERGENCY_FUND_TAG.id ? f.FUND_MEMBERSHIP : undefined,
      isError: false,
    }),
  }
})
vi.mock('../../api/guide', () => ({
  useSetBinding: () => ({ mutateAsync: state.dismiss, isPending: false }),
}))

import { EmergencyFundPicker } from './EmergencyFundPicker'

/** Rendered inside a router: the surface links into the Guide. */
const render = (ui: ReactElement) => rtlRender(ui, { wrapper: MemoryRouter })

function show(from?: 'guide') {
  const onClose = vi.fn()
  render(<EmergencyFundPicker budgetId="b1" from={from} onClose={onClose} />)
  return onClose
}

const amount = () => screen.getByLabelText(/Amount \(optional\)/)

beforeEach(async () => {
  await new Promise((r) => setTimeout(r, 0))
  await new Promise((r) => setTimeout(r, 0))
  window.history.replaceState(null, '')
  state.picker = FUND_PICKER as PickerData
  state.save.mockReset().mockResolvedValue({})
  state.dismiss.mockReset().mockResolvedValue({})
  expect(EMERGENCY_FUND_TAG.system_key).toBe('emergency_fund')
})

describe('EmergencyFundPicker', () => {
  it('opens on what is chosen now', () => {
    show()
    expect(screen.getByRole('checkbox', { name: /Emergency Fund/ })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: /Harborstone Reserve/ })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: /Cascade Point HYSA/ })).not.toBeChecked()
    expect(screen.getByRole('checkbox', { name: /somewhere IGAB doesn’t track/ })).toBeChecked()
    expect(amount()).toHaveValue('1000')
    expect(screen.getByLabelText(/Note/)).toHaveValue('credit union')
    expect(
      screen.getByText(/on-budget account’s money is already in its envelopes/)
    ).toBeInTheDocument()
  })

  it('sends one payload: envelope diff, modes, the full account set and the external part', async () => {
    const onClose = show()
    fireEvent.click(screen.getByRole('checkbox', { name: /Groceries/ }))
    fireEvent.change(screen.getByRole('combobox', { name: 'Groceries counts as saved' }), {
      target: { value: 'sent_out' },
    })
    fireEvent.click(screen.getByRole('checkbox', { name: /Cascade Point HYSA/ }))
    fireEvent.change(amount(), { target: { value: '1,250.50' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(state.save).toHaveBeenCalledTimes(1))
    expect(state.save.mock.calls[0][0]).toEqual({
      add_categories: ['groceries'],
      remove_categories: [],
      savings_modes: { groceries: 'sent_out' },
      account_ids: ['hysa', 'reserve'],
      external: { declared: true, amount: '1250.50', note: 'credit union' },
    })
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('says a chosen account will also count as savings', () => {
    show()
    expect(screen.queryByText('Also turns on Counts as savings')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: /Cascade Point HYSA/ }))
    const row = screen.getByRole('checkbox', { name: /Cascade Point HYSA/ }).closest('li')!
    expect(within(row).getByText('Also turns on Counts as savings')).toBeInTheDocument()
  })

  it('an unreadable kept-elsewhere amount says so inline and blocks Save — never books zero', async () => {
    show()
    fireEvent.change(amount(), { target: { value: 'most of it' } })
    expect(amount()).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText(/Enter an amount like 1,000/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Fix the amount kept elsewhere first')).toBeInTheDocument()
    expect(state.save).not.toHaveBeenCalled()
  })

  it('a blank amount is "I have this covered", sent as null', async () => {
    show()
    fireEvent.change(amount(), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(state.save).toHaveBeenCalled())
    expect(state.save.mock.calls[0][0].external).toEqual({
      declared: true,
      amount: null,
      note: 'credit union',
    })
  })

  it('unticking kept elsewhere sends no figure and no note', async () => {
    show()
    fireEvent.click(screen.getByRole('checkbox', { name: /somewhere IGAB doesn’t track/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(state.save).toHaveBeenCalled())
    expect(state.save.mock.calls[0][0].external).toEqual({
      declared: false,
      amount: null,
      note: null,
    })
  })

  it('offers "Don’t track this in the Guide" only when opened from the Guide', async () => {
    show()
    expect(screen.queryByRole('button', { name: /Don’t track/ })).not.toBeInTheDocument()
  })

  it('from the Guide, Don’t track writes the Guide’s dismissal', async () => {
    const onClose = show('guide')
    fireEvent.click(screen.getByRole('button', { name: 'Don’t track this in the Guide' }))
    await waitFor(() =>
      expect(state.dismiss).toHaveBeenCalledWith({
        conceptKey: 'emergency_fund',
        mode: 'dismissed',
      })
    )
    expect(state.save).not.toHaveBeenCalled()
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('stays open and says why when the save is refused', async () => {
    state.save.mockRejectedValue(new Error('refused'))
    const onClose = show()
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText(/Could not save what the fund counts/)).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
  })

  it('keeps the membership rows it was given', () => {
    show()
    expect(FUND_MEMBERSHIP.categories).toHaveLength(2)
    expect(
      screen.getByRole('group', { name: 'Envelopes tagged Emergency fund' })
    ).toBeInTheDocument()
  })
})
