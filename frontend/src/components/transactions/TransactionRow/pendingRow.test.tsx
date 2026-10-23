/**
 * A pending row is on its way, not waiting on the person: it shows no
 * unapproved eye and offers no Approve — the served `awaiting_approval` says
 * so — and "Enter Now" takes it out of pending and approves it in one step.
 * Entered alone, it became posted-and-unapproved, and the account asked to
 * approve the row the person had just acted on.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TransactionRow } from './TransactionRow'
import type { Transaction } from '../../../types'
import { makeTransaction } from '../../../test-utils/factories'

const update = vi.hoisted(() => vi.fn())
vi.mock('../../../api/transactions', () => ({
  useUpdateTransaction: () => ({ mutate: update, mutateAsync: vi.fn(), isPending: false }),
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

function hold(overrides: Partial<Transaction> = {}): Transaction {
  return makeTransaction({
    cleared: 'pending',
    approved: false,
    awaiting_approval: false,
    ...overrides,
  })
}

function renderRow(t: Transaction) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <TransactionRow
          transaction={t}
          onEdit={vi.fn()}
          payeeMap={new Map()}
          accountMap={new Map()}
          categoryLabels={new Map()}
          payees={[]}
          accounts={[]}
          categories={[]}
          categoryGroups={[]}
          isSelected={false}
          orderedIds={[t.id]}
          onSelect={vi.fn()}
          onStartSplit={vi.fn()}
          onDuplicate={vi.fn()}
          onMakeRepeating={vi.fn()}
          onMakeTransfer={vi.fn()}
        />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => update.mockClear())

describe('a pending row', () => {
  it('shows no unapproved eye', () => {
    renderRow(hold())
    expect(screen.queryByLabelText('Unapproved transaction')).not.toBeInTheDocument()
  })

  it('offers Enter Now and not Approve', () => {
    const { container } = renderRow(hold())
    fireEvent.contextMenu(container.querySelector('.transaction-row')!)
    expect(screen.getByText('Enter Now')).toBeInTheDocument()
    expect(screen.queryByText('Approve')).not.toBeInTheDocument()
  })

  it('is entered and approved in one step by Enter Now', () => {
    const { container } = renderRow(hold())
    fireEvent.contextMenu(container.querySelector('.transaction-row')!)
    fireEvent.click(screen.getByText('Enter Now'))
    expect(update).toHaveBeenCalledWith(
      expect.objectContaining({ cleared: 'uncleared', approved: true })
    )
  })
})

describe('a posted row waiting on the person', () => {
  it('shows the eye and offers Approve', () => {
    const { container } = renderRow(
      makeTransaction({ cleared: 'uncleared', approved: false, awaiting_approval: true })
    )
    expect(screen.getByLabelText('Unapproved transaction')).toBeInTheDocument()
    fireEvent.contextMenu(container.querySelector('.transaction-row')!)
    expect(screen.getByText('Approve')).toBeInTheDocument()
  })
})
