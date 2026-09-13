/**
 * The copy dialog offers one real choice: what to do with the past.
 *
 * Everything else about a copy — new ids, no bank link, the same
 * arrangement — is what a copy always is, and the dialog does not pretend
 * otherwise. A structure-only copy sends the date it starts from; a full
 * one does not, because it has no start.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { mutateAsync } = vi.hoisted(() => ({ mutateAsync: vi.fn() }))
vi.mock('../../api/budgetSnapshots', () => ({
  useCloneBudget: () => ({ mutateAsync, isPending: false }),
}))
vi.mock('../common/Dialog/Dialog', () => ({
  Dialog: ({
    title,
    children,
    footer,
  }: {
    title: string
    children: React.ReactNode
    footer?: React.ReactNode
  }) => (
    <div>
      <h2>{title}</h2>
      {children}
      {footer}
    </div>
  ),
}))

import { CloneBudgetModal } from './CloneBudgetModal'

beforeEach(() => {
  mutateAsync.mockReset()
  mutateAsync.mockResolvedValue({ budget_id: 'b2', budget_name: 'Household copy' })
})

function open(onClose = vi.fn()) {
  render(<CloneBudgetModal budgetId="b1" budgetName="Household" onClose={onClose} />)
  return onClose
}

describe('CloneBudgetModal', () => {
  it('copies everything by default, with no start date to send', async () => {
    const onClose = open()
    await userEvent.click(screen.getByRole('button', { name: /copy budget/i }))
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled())
    expect(mutateAsync.mock.calls[0][0]).toMatchObject({
      budgetId: 'b1',
      name: 'Household copy',
      structure_only: false,
      as_of: undefined,
    })
    expect(onClose).toHaveBeenCalled()
  })

  it('a structure-only copy asks what day it starts from and sends it', async () => {
    open()
    expect(screen.queryByLabelText(/starting from/i)).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('radio', { name: /structure only/i }))
    const date = screen.getByLabelText(/starting from/i)
    await userEvent.clear(date)
    await userEvent.type(date, '2026-08-31')
    await userEvent.click(screen.getByRole('button', { name: /copy budget/i }))
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled())
    expect(mutateAsync.mock.calls[0][0]).toMatchObject({
      structure_only: true,
      as_of: '2026-08-31',
    })
  })

  it('an emptied name sends none, so the server names the copy', async () => {
    open()
    await userEvent.clear(screen.getByDisplayValue('Household copy'))
    await userEvent.click(screen.getByRole('button', { name: /copy budget/i }))
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled())
    expect(mutateAsync.mock.calls[0][0].name).toBeUndefined()
  })

  it('a structure-only copy with its date cleared asks for one instead of sending', async () => {
    open()
    await userEvent.click(screen.getByRole('radio', { name: /structure only/i }))
    await userEvent.clear(screen.getByLabelText(/starting from/i))
    const submit = screen.getByRole('button', { name: /copy budget/i })
    // Enabled while empty: the answer is a sentence, not a greyed-out button.
    expect(submit).toBeEnabled()
    await userEvent.click(submit)
    expect(screen.getByText('Pick the day the copy starts from')).toBeInTheDocument()
    expect(mutateAsync).not.toHaveBeenCalled()
  })
})
