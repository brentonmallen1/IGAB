/**
 * "Counts toward emergency fund" is offered only where Counts as savings is —
 * an off-budget asset — and only once that is on, because the server refuses
 * the mark on any other shape. The modals clear it when Counts as savings goes
 * off and send it as false wherever it cannot apply.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CountsTowardEmergencyFundField } from './CountsTowardEmergencyFundField'
import { savingsFlagsPayload } from './useSavingsFlags'
import { AddAccountModal } from './AddAccountModal'
import { useAppStore } from '../../stores/appStore'

const createMutate = vi.hoisted(() => vi.fn((_: unknown) => Promise.resolve({})))
vi.mock('../../api/accounts', () => ({
  useCreateAccount: () => ({ mutateAsync: createMutate, isPending: false }),
}))
vi.mock('../../api/accountTypes', () => ({
  useAccountTypes: () => ({ data: undefined }),
}))

const mark = () =>
  screen.queryByRole('checkbox', {
    name: 'Counts toward emergency fund',
  }) as HTMLInputElement | null
const saves = () => screen.getByRole('checkbox', { name: 'Counts as savings' }) as HTMLInputElement

function field(over: Partial<Parameters<typeof CountsTowardEmergencyFundField>[0]> = {}) {
  return render(
    <CountsTowardEmergencyFundField
      onBudget={false}
      classification="asset"
      countsAsSavings
      checked={false}
      onChange={vi.fn()}
      {...over}
    />
  )
}

beforeEach(async () => {
  await new Promise((r) => setTimeout(r, 0))
  await new Promise((r) => setTimeout(r, 0))
  window.history.replaceState(null, '')
  createMutate.mockClear()
  useAppStore.setState({ currentBudgetId: 'b1' })
})

describe('CountsTowardEmergencyFundField', () => {
  it('is offered on an off-budget asset that counts as savings', () => {
    field()
    expect(mark()).toBeEnabled()
    expect(
      screen.getByText(
        'Its whole balance is part of your emergency fund. For an account holding several things, keep it on budget and tag the envelopes instead.'
      )
    ).toBeInTheDocument()
  })

  it('is not offered on budget or on a liability', () => {
    field({ onBudget: true })
    expect(mark()).toBeNull()
    field({ classification: 'liability' })
    expect(mark()).toBeNull()
  })

  it('is disabled, unchecked and says why until Counts as savings is on', () => {
    field({ countsAsSavings: false, checked: true })
    expect(mark()).toBeDisabled()
    expect(mark()?.checked).toBe(false)
    expect(screen.getByText('Turn on Counts as savings first')).toBeInTheDocument()
  })

  it('reports a click', async () => {
    const onChange = vi.fn()
    field({ onChange })
    await userEvent.click(mark()!)
    expect(onChange).toHaveBeenCalledWith(true)
  })
})

describe('savingsFlagsPayload', () => {
  const on = { countsAsSavings: true, countsTowardEmergencyFund: true }

  it('sends the mark on an off-budget savings asset', () => {
    expect(savingsFlagsPayload(on, { onBudget: false, classification: 'asset' })).toEqual({
      counts_as_savings: true,
      counts_toward_emergency_fund: true,
    })
  })

  it('sends it as false wherever the server would refuse it', () => {
    const flag = (flags: typeof on, onBudget: boolean, classification: 'asset' | 'liability') =>
      savingsFlagsPayload(flags, { onBudget, classification }).counts_toward_emergency_fund
    expect(flag(on, true, 'asset')).toBe(false)
    expect(flag(on, false, 'liability')).toBe(false)
    expect(flag({ ...on, countsAsSavings: false }, false, 'asset')).toBe(false)
  })
})

describe('AddAccountModal emergency-fund mark', () => {
  it('turning Counts as savings off clears it', async () => {
    render(<AddAccountModal onClose={vi.fn()} initialTypeKey="savings" />)
    await userEvent.click(screen.getByRole('checkbox', { name: 'On budget' }))
    await userEvent.click(mark()!)
    expect(mark()?.checked).toBe(true)

    await userEvent.click(saves())
    await userEvent.click(saves())

    expect(mark()?.checked).toBe(false)
  })

  it('sends the choice with the new account', async () => {
    render(<AddAccountModal onClose={vi.fn()} initialTypeKey="savings" />)
    await userEvent.type(screen.getByPlaceholderText('e.g. Chase Checking'), 'Harborstone Reserve')
    await userEvent.click(screen.getByRole('checkbox', { name: 'On budget' }))
    await userEvent.click(mark()!)
    await userEvent.click(screen.getByRole('button', { name: 'Create Account' }))
    expect(createMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        account_type: 'savings',
        on_budget: false,
        counts_as_savings: true,
        counts_toward_emergency_fund: true,
      })
    )
  })

  it('sends false for an account put back on budget', async () => {
    render(<AddAccountModal onClose={vi.fn()} initialTypeKey="savings" />)
    await userEvent.type(screen.getByPlaceholderText('e.g. Chase Checking'), 'Harborstone Reserve')
    await userEvent.click(screen.getByRole('checkbox', { name: 'On budget' }))
    await userEvent.click(mark()!)
    await userEvent.click(screen.getByRole('checkbox', { name: 'On budget' }))
    await userEvent.click(screen.getByRole('button', { name: 'Create Account' }))
    expect(createMutate).toHaveBeenCalledWith(
      expect.objectContaining({ on_budget: true, counts_toward_emergency_fund: false })
    )
  })
})
