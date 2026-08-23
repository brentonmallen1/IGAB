/**
 * The "AI extracted, needs review" marker. Its whole job is to separate an
 * AI-drafted row from an unapproved bank import — both of which are dimmed and
 * carry the warning eye — so the cases that must NOT show it matter as much as
 * the one that must.
 */
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TransactionRow } from './TransactionRow'
import type { Transaction } from '../../../types'

vi.mock('../../../api/transactions', () => ({
  useUpdateTransaction: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
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

const MARKER = 'Extracted from an image by AI — needs review'

function txn(overrides: Partial<Transaction> = {}): Transaction {
  return {
    id: 't1',
    budget_id: 'b1',
    account_id: 'a1',
    date: '2026-08-02',
    amount: -12.5,
    payee_id: null,
    category_id: null,
    memo: null,
    cleared: 'uncleared',
    approved: false,
    created_via: 'ai_receipt',
    is_split: false,
    transfer_id: null,
    has_sync_source: false,
    ...overrides,
  } as unknown as Transaction
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
          categoryMap={new Map()}
          payees={[]}
          categories={[]}
          categoryGroups={[]}
          isSelected={false}
          orderedIds={[t.id]}
          onSelect={vi.fn()}
          onStartSplit={vi.fn()}
          onDuplicate={vi.fn()}
          onMakeRepeating={vi.fn()}
        />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('AI needs-review marker', () => {
  it('marks an unapproved receipt-extracted transaction', () => {
    renderRow(txn())
    expect(screen.getByLabelText(MARKER)).toBeInTheDocument()
  })

  it('marks an unapproved natural-language transaction too', () => {
    renderRow(txn({ created_via: 'ai_nl' }))
    expect(screen.getByLabelText(MARKER)).toBeInTheDocument()
  })

  it('drops away once approved — the marker means "this needs you"', () => {
    renderRow(txn({ approved: true }))
    expect(screen.queryByLabelText(MARKER)).not.toBeInTheDocument()
  })

  it('does not mark an unapproved bank import', () => {
    // The case the marker exists to distinguish: same dimmed row, same warning
    // eye, but nothing was read off a photo.
    renderRow(txn({ created_via: null }))
    expect(screen.queryByLabelText(MARKER)).not.toBeInTheDocument()
    expect(screen.getByLabelText('Unapproved transaction')).toBeInTheDocument()
  })

  it('sits alongside the unapproved eye rather than replacing it', () => {
    renderRow(txn())
    expect(screen.getByLabelText(MARKER)).toBeInTheDocument()
    expect(screen.getByLabelText('Unapproved transaction')).toBeInTheDocument()
  })
})
