/**
 * The payee cell's transfer group: converting a row to a transfer without
 * leaving the register.
 *
 * The cell hides transfer payees on purpose — picking one names a transfer
 * the row is not — but a payee genuinely called "Online Transfer" is a real
 * payee and is offered, so the list gave no way to tell a name from a
 * destination. These options are destinations, under their own heading, and
 * they hand the row to the conversion dialog rather than writing a payee id.
 */
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TransactionRow } from './TransactionRow'
import type { Account, Payee, Transaction } from '../../../types'

const updateMutate = vi.fn()
vi.mock('../../../api/transactions', () => ({
  useUpdateTransaction: () => ({ mutate: updateMutate, mutateAsync: vi.fn(), isPending: false }),
  useDeleteTransaction: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
  useUnreconcileTransaction: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock('../../../api/attachments', () => ({
  confirmDeleteTransaction: vi.fn(),
  useAttachmentUrl: () => ({ data: null }),
  useCheckAttachments: () => ({ data: {} }),
  ATTACHMENT_ACCEPT: 'image/*,application/pdf',
  isAttachableFile: () => true,
  uploadFilesToTransaction: vi.fn(),
}))
vi.mock('../../../api/categories', () => ({ useCreateCategory: () => ({ mutateAsync: vi.fn() }) }))
vi.mock('../../../api/payees', () => ({ useCreatePayee: () => ({ mutateAsync: vi.fn() }) }))
vi.mock('./RowAttachmentButton', () => ({ RowAttachmentButton: () => null }))
vi.mock('../../simplefin/BankRecordIcon', () => ({ BankRecordIcon: () => null }))

const accounts = [
  { id: 'a1', name: 'Harborstone Checking', is_closed: false },
  { id: 'a2', name: 'Sapphire Visa', is_closed: false },
] as unknown as Account[]

const payees = [
  { id: 'p1', name: 'Online Transfer', transfer_account_id: null },
  { id: 'p2', name: 'Transfer : Sapphire Visa', transfer_account_id: 'a2' },
] as unknown as Payee[]

function txn(overrides: Partial<Transaction> = {}): Transaction {
  return {
    id: 't1',
    budget_id: 'b1',
    account_id: 'a1',
    date: '2026-09-08',
    amount: -17.09,
    payee_id: null,
    category_id: null,
    memo: null,
    cleared: 'uncleared',
    approved: true,
    created_via: null,
    is_split: false,
    transfer_id: null,
    has_sync_source: false,
    needs_category: false,
    ...overrides,
  } as unknown as Transaction
}

function openPayeeCell(t: Transaction, onMakeTransfer = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const { container } = render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <TransactionRow
          transaction={t}
          onEdit={vi.fn()}
          payeeMap={new Map()}
          accountMap={new Map([['a2', 'Sapphire Visa']])}
          categoryMap={new Map()}
          payees={payees}
          accounts={accounts}
          categories={[]}
          categoryGroups={[]}
          isSelected={false}
          orderedIds={[t.id]}
          onSelect={vi.fn()}
          onStartSplit={vi.fn()}
          onDuplicate={vi.fn()}
          onMakeRepeating={vi.fn()}
          onMakeTransfer={onMakeTransfer}
          accountOnBudget
        />
      </MemoryRouter>
    </QueryClientProvider>
  )
  const cell = container.querySelector('.txn-col--payee') as HTMLElement
  fireEvent.click(cell)
  return { cell, onMakeTransfer }
}

describe('the payee cell’s transfer destinations', () => {
  it('offers every other open account under its own heading', () => {
    openPayeeCell(txn())
    const heading = screen.getByText('Transfer to account')
    expect(heading).toBeTruthy()
    const group = heading.closest('.combobox__group') as HTMLElement
    expect(within(group).getByText('Sapphire Visa')).toBeTruthy()
    // The row's own account is not a destination.
    expect(within(group).queryByText('Harborstone Checking')).toBeNull()
  })

  it('still hides transfer payees, and still offers a payee merely named like one', () => {
    openPayeeCell(txn())
    expect(screen.queryByText('Transfer : Sapphire Visa')).toBeNull()
    expect(screen.getByText('Online Transfer')).toBeTruthy()
  })

  it('opens the conversion instead of writing a payee id', () => {
    const { onMakeTransfer } = openPayeeCell(txn())
    const group = screen.getByText('Transfer to account').closest('.combobox__group') as HTMLElement
    fireEvent.mouseDown(within(group).getByText('Sapphire Visa'))
    expect(onMakeTransfer).toHaveBeenCalledWith(expect.objectContaining({ id: 't1' }), 'a2')
    expect(updateMutate).not.toHaveBeenCalled()
  })

  it('picking a real payee still commits a payee id', () => {
    const { onMakeTransfer } = openPayeeCell(txn())
    fireEvent.mouseDown(screen.getByText('Online Transfer'))
    expect(onMakeTransfer).not.toHaveBeenCalled()
    expect(updateMutate).toHaveBeenCalledWith(expect.objectContaining({ payee_id: 'p1' }))
  })

  it('offers no destinations on a row that cannot be converted', () => {
    openPayeeCell(txn({ is_split: true }))
    expect(screen.queryByText('Transfer to account')).toBeNull()
  })
})
