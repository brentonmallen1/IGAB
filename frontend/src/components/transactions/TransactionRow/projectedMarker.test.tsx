/**
 * The projected-interest badge. The server writes a loan's monthly interest
 * row from its terms and serves `projected_interest_month` on it; the row
 * says so, and stops saying so the moment the person adopts the row (an edit
 * that clears the month) — which is also why the field is in the memo
 * comparator: an adoption can move nothing else the row compares.
 */
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TransactionRow } from './TransactionRow'
import type { Transaction } from '../../../types'
import { PROJECTED_INTEREST_LABEL } from '../../../utils/projectedInterest'

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

function txn(overrides: Partial<Transaction> = {}): Transaction {
  return {
    id: 't1',
    budget_id: 'b1',
    account_id: 'loan',
    date: '2026-03-15',
    amount: -120,
    payee_id: null,
    category_id: null,
    memo: null,
    cleared: 'uncleared',
    approved: true,
    created_via: 'projection',
    is_split: false,
    transfer_id: null,
    has_sync_source: false,
    needs_category: false,
    projected_interest_month: '2026-03-01',
    ...overrides,
  } as unknown as Transaction
}

// Every prop but the transaction is held stable across renders, so a
// re-render can only come from the memo comparator seeing the row change.
const STABLE = {
  onEdit: vi.fn(),
  payeeMap: new Map(),
  accountMap: new Map(),
  categoryMap: new Map(),
  payees: [],
  accounts: [],
  categories: [],
  categoryGroups: [],
  orderedIds: ['t1'],
  onSelect: vi.fn(),
  onStartSplit: vi.fn(),
  onDuplicate: vi.fn(),
  onMakeRepeating: vi.fn(),
  onMakeTransfer: vi.fn(),
}

function row(t: Transaction) {
  return <TransactionRow transaction={t} isSelected={false} {...STABLE} />
}

function renderRow(t: Transaction) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrap = (node: React.ReactNode) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>
  )
  const utils = render(wrap(row(t)))
  return { ...utils, rerenderRow: (next: Transaction) => utils.rerender(wrap(row(next))) }
}

describe('projected interest badge', () => {
  it('marks a projection', () => {
    renderRow(txn())
    expect(screen.getByLabelText(PROJECTED_INTEREST_LABEL)).toBeInTheDocument()
  })

  it('does not mark the lender’s own interest row', () => {
    renderRow(txn({ projected_interest_month: null, created_via: 'sync' }))
    expect(screen.queryByLabelText(PROJECTED_INTEREST_LABEL)).not.toBeInTheDocument()
  })

  it('drops away when the row is adopted, though nothing else on it moved', () => {
    const { rerenderRow } = renderRow(txn())
    expect(screen.getByLabelText(PROJECTED_INTEREST_LABEL)).toBeInTheDocument()
    rerenderRow(txn({ projected_interest_month: null }))
    expect(screen.queryByLabelText(PROJECTED_INTEREST_LABEL)).not.toBeInTheDocument()
  })
})
