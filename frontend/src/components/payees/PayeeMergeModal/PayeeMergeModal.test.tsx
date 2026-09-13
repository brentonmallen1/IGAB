/**
 * Merge stays enabled and names what it is waiting for.
 *
 * It was disabled until the target and the pattern both checked out, so an
 * invalid regex three sections up — or a custom name never typed — left a
 * greyed button and no word as to which part was wrong.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { PayeeWithCount } from '../../../api/payees'
import { PayeeMergeModal } from './PayeeMergeModal'

vi.mock('../../../api/ai', () => ({
  useAIStatus: () => ({ data: { available: false } }),
  useSuggestRegex: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

function payee(id: string, name: string, count: number): PayeeWithCount {
  return {
    id,
    name,
    transaction_count: count,
    last_used: null,
    mapping_samples: [],
    match_pattern: null,
    transfer_account_id: null,
  } as unknown as PayeeWithCount
}

const group = [payee('p1', 'Nordstrom #0412', 6), payee('p2', 'NORDSTROM ONLINE', 2)]

beforeEach(async () => {
  // Every test opens a Dialog; drain the deferred history.back() of the last.
  await new Promise((r) => setTimeout(r, 0))
  await new Promise((r) => setTimeout(r, 0))
  window.history.replaceState(null, '')
})

function renderModal() {
  const onConfirm = vi.fn()
  render(
    <PayeeMergeModal
      payees={group}
      allPayees={group}
      onConfirm={onConfirm}
      onCancel={vi.fn()}
      isPending={false}
    />
  )
  return { onConfirm }
}

const mergeButton = () => screen.getByRole('button', { name: 'Merge 2 payees' })

describe('PayeeMergeModal', () => {
  it('merges into the busiest name by default', async () => {
    const { onConfirm } = renderModal()
    await userEvent.click(mergeButton())
    expect(onConfirm).toHaveBeenCalledWith(expect.objectContaining({ targetId: 'p1' }))
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('asks for the custom name instead of sitting disabled', async () => {
    const { onConfirm } = renderModal()
    await userEvent.click(screen.getByText('Enter a custom name…'))
    expect(mergeButton()).toBeEnabled()
    await userEvent.click(mergeButton())
    expect(screen.getByRole('alert')).toHaveTextContent('Enter the new name')
    expect(onConfirm).not.toHaveBeenCalled()
    // Derived, not stored: typing the name clears it.
    await userEvent.type(screen.getByLabelText('New name'), 'Nordstrom')
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('names an invalid pattern as the thing to fix', async () => {
    const { onConfirm } = renderModal()
    await userEvent.click(screen.getByLabelText(/Set a match pattern/))
    const input = screen.getByLabelText('Match pattern')
    // fireEvent: userEvent reads '[' as the start of a key descriptor.
    fireEvent.change(input, { target: { value: 'NORD[' } })
    await userEvent.click(mergeButton())
    expect(screen.getByRole('alert')).toHaveTextContent('Fix the match pattern')
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('does not nag before the first press', () => {
    renderModal()
    expect(screen.queryByRole('alert')).toBeNull()
  })
})
