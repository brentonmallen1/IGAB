/**
 * Converting one row to a transfer from the register.
 *
 * The request it sends is the editor's request — same fields, same refusal
 * to carry money alongside a link (TransactionService.update refuses that,
 * and refused every editor conversion for a month because the editor
 * restated an unchanged amount). And the far-leg question is never guessed:
 * with candidates on the table, the dialog holds the save and says why.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MakeTransferDialog } from './MakeTransferDialog'
import type { Account, Transaction } from '../../../types'

const mutateAsync = vi.fn().mockResolvedValue({})
let candidates: Partial<Transaction>[] = []

vi.mock('../../../api/transactions', () => ({
  useUpdateTransaction: () => ({ mutateAsync, isPending: false }),
  useTransferCandidates: () => ({ data: candidates }),
}))

const accounts = [
  { id: 'a1', name: 'Harborstone Checking', is_closed: false },
  { id: 'a2', name: 'Sapphire Visa', is_closed: false },
  { id: 'a3', name: 'Cascade Point HYSA', is_closed: true },
] as unknown as Account[]

const txn = {
  id: 't1',
  account_id: 'a1',
  date: '2026-09-08',
  amount: -17.09,
  memo: null,
  cleared: 'cleared',
} as unknown as Transaction

function open(initialAccountId = '') {
  const onClose = vi.fn()
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <MakeTransferDialog
        budgetId="b1"
        transaction={txn}
        accounts={accounts}
        initialAccountId={initialAccountId}
        onClose={onClose}
      />
    </QueryClientProvider>
  )
  return { onClose }
}

describe('MakeTransferDialog', () => {
  beforeEach(() => {
    mutateAsync.mockClear()
    candidates = []
  })

  it('sends the link alone — never the row’s money', async () => {
    const { onClose } = open('a2')
    fireEvent.click(screen.getByText('Make transfer'))
    await vi.waitFor(() => expect(mutateAsync).toHaveBeenCalled())
    expect(mutateAsync).toHaveBeenCalledWith({ id: 't1', transfer_account_id: 'a2' })
    await vi.waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('offers every other open account, and not the row’s own or a closed one', () => {
    open()
    const select = screen.getByLabelText('Transfer account') as HTMLSelectElement
    const names = Array.from(select.options).map((o) => o.textContent)
    expect(names).toContain('Sapphire Visa')
    expect(names).not.toContain('Harborstone Checking')
    expect(names).not.toContain('Cascade Point HYSA')
  })

  it('says what is missing rather than disabling the button', () => {
    open()
    fireEvent.click(screen.getByText('Make transfer'))
    expect(screen.getByText('Pick the account this money moved to or from.')).toBeTruthy()
    expect(mutateAsync).not.toHaveBeenCalled()
  })

  it('holds the save until the ambiguous far leg is named', async () => {
    candidates = [{ id: 'c1', date: '2026-09-09', amount: 17.09, memo: null, cleared: 'cleared' }]
    open('a2')
    fireEvent.click(screen.getByText('Make transfer'))
    expect(
      screen.getByText('Say which transaction in Sapphire Visa is the other side.')
    ).toBeTruthy()
    expect(mutateAsync).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('radio', { name: /2026-09-09/ }))
    fireEvent.click(screen.getByText('Make transfer'))
    await vi.waitFor(() => expect(mutateAsync).toHaveBeenCalled())
    expect(mutateAsync).toHaveBeenCalledWith({
      id: 't1',
      transfer_account_id: 'a2',
      transfer_partner_transaction_id: 'c1',
    })
  })

  it('asks for the far leg to be written when none of them is it', async () => {
    candidates = [{ id: 'c1', date: '2026-09-09', amount: 17.09, memo: null, cleared: 'cleared' }]
    open('a2')
    fireEvent.click(screen.getByRole('radio', { name: /None of these/ }))
    fireEvent.click(screen.getByText('Make transfer'))
    await vi.waitFor(() => expect(mutateAsync).toHaveBeenCalled())
    expect(mutateAsync).toHaveBeenCalledWith({
      id: 't1',
      transfer_account_id: 'a2',
      transfer_create_partner: true,
    })
  })
})
