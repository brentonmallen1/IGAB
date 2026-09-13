/**
 * The schedule editor's Create stays enabled and says what is missing.
 *
 * It leaned on `required` for the account and the date, so a press with no
 * account drew the browser's own bubble beside a select the pinned footer's
 * button is nowhere near — and on a phone, nothing at all. Now every check is
 * the submit handler's, and its message sits in the footer beside the button.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ScheduledTransactionEditor } from './ScheduledTransactionEditor'

const { create, update } = vi.hoisted(() => ({ create: vi.fn(), update: vi.fn() }))

vi.mock('../../api/accounts', () => ({
  useAccounts: () => ({ data: [{ id: 'a1', name: 'Harborstone Checking' }] }),
}))
vi.mock('../../api/categories', () => ({
  useCategories: () => ({ data: [] }),
  useCategoryGroups: () => ({ data: [] }),
}))
vi.mock('../../api/scheduledTransactions', () => ({
  useCreateScheduledTransaction: () => ({ mutateAsync: create, isPending: false }),
  useUpdateScheduledTransaction: () => ({ mutateAsync: update, isPending: false }),
  useDeleteScheduledTransaction: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

beforeEach(async () => {
  // Every test opens a Dialog; drain the deferred history.back() of the last.
  await new Promise((r) => setTimeout(r, 0))
  await new Promise((r) => setTimeout(r, 0))
  window.history.replaceState(null, '')
  create.mockReset().mockResolvedValue({})
  update.mockReset().mockResolvedValue({})
})

function renderEditor(initial?: { account_id?: string; amount?: number }) {
  const onClose = vi.fn()
  render(
    <ScheduledTransactionEditor budgetId="b1" existing={null} initial={initial} onClose={onClose} />
  )
  return { onClose }
}

const createButton = () => screen.getByRole('button', { name: 'Create' })

describe('ScheduledTransactionEditor', () => {
  it('labels every field by its sentence-case name', () => {
    renderEditor()
    for (const name of ['Account', 'Type', 'Amount', 'Frequency', 'Start date', 'End date']) {
      expect(screen.getByLabelText(name)).toBeInTheDocument()
    }
    expect(screen.getByLabelText('Auto-create transaction when due')).toHaveAttribute(
      'type',
      'checkbox'
    )
  })

  it('keeps Create enabled with no account, and asks for one on press', async () => {
    renderEditor()
    expect(createButton()).toBeEnabled()
    await userEvent.type(screen.getByLabelText('Amount'), '40')
    await userEvent.click(createButton())
    expect(screen.getByRole('alert')).toHaveTextContent('Choose the account')
    expect(create).not.toHaveBeenCalled()
  })

  it('refuses an unreadable or zero amount rather than scheduling $0.00', async () => {
    renderEditor({ account_id: 'a1' })
    await userEvent.click(createButton())
    expect(screen.getByRole('alert')).toHaveTextContent('Enter an amount.')
    await userEvent.type(screen.getByLabelText('Amount'), '0')
    await userEvent.click(createButton())
    expect(screen.getByRole('alert')).toHaveTextContent('Enter an amount.')
    expect(create).not.toHaveBeenCalled()
  })

  it('asks for the date when it was cleared', async () => {
    renderEditor({ account_id: 'a1', amount: -40 })
    await userEvent.clear(screen.getByLabelText('Start date'))
    await userEvent.click(createButton())
    expect(screen.getByRole('alert')).toHaveTextContent('Enter the start date.')
    expect(create).not.toHaveBeenCalled()
  })

  it('creates an outflow as a negative amount and closes', async () => {
    const { onClose } = renderEditor({ account_id: 'a1' })
    await userEvent.type(screen.getByLabelText('Amount'), '12.50')
    await userEvent.click(createButton())
    expect(create).toHaveBeenCalledWith(
      expect.objectContaining({ account_id: 'a1', amount: -12.5, frequency: 'monthly' })
    )
    expect(onClose).toHaveBeenCalled()
    expect(screen.queryByRole('alert')).toBeNull()
  })
})
