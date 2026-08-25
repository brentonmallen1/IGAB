/**
 * The category cell's four states — and specifically that the amber
 * "Needs Category" chip follows the server's `needs_category`, never a rule
 * rebuilt here.
 *
 * It used to read `transfer_id !== null`, which recognises only a transfer
 * whose partner also imported. A YNAB export routinely writes legs whose
 * partner never arrives, and every one of them wore the chip — the register
 * nagging about ~930 rows the backend had already agreed were fine.
 */
import { describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'
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
    approved: true,
    created_via: null,
    is_split: false,
    transfer_id: null,
    has_sync_source: false,
    needs_category: false,
    ...overrides,
  } as unknown as Transaction
}

/** The payee column renders "Transfer : …" and an em dash of its own, so every
 *  assertion here is scoped to the category cell. */
function categoryCell(t: Transaction, accountOnBudget = true): string {
  const { container } = renderRow(t, accountOnBudget)
  return container.querySelector('.txn-col--category')?.textContent?.trim() ?? ''
}

function renderRow(t: Transaction, accountOnBudget = true) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <TransactionRow
          transaction={t}
          onEdit={vi.fn()}
          payeeMap={new Map()}
          accountMap={new Map()}
          categoryMap={new Map([['c1', 'Groceries']])}
          payees={[]}
          categories={[]}
          categoryGroups={[]}
          isSelected={false}
          orderedIds={[t.id]}
          onSelect={vi.fn()}
          onStartSplit={vi.fn()}
          onDuplicate={vi.fn()}
          onMakeRepeating={vi.fn()}
          accountOnBudget={accountOnBudget}
        />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('the category cell', () => {
  it('shows the category when there is one', () => {
    expect(categoryCell(txn({ category_id: 'c1' }))).toBe('Groceries')
  })

  it('chips a row the server says needs filing', () => {
    expect(categoryCell(txn({ needs_category: true }))).toBe('Needs Category')
  })

  it('reads a category-less on-budget row the server cleared as a transfer', () => {
    expect(categoryCell(txn({ transfer_id: 'other', needs_category: false }))).toBe('Transfer')
  })

  it('says nothing on a tracking account, which has no categories', () => {
    expect(categoryCell(txn({ needs_category: false }), false)).toBe('—')
  })
})

describe('a transfer leg whose partner never imported', () => {
  // The regression. `transfer_id` is null because the pair never matched, but
  // the payee names another on-budget account, so the server said no category
  // is needed. The old local rule saw a null transfer_id and chipped it.
  const unpaired = txn({ transfer_id: null, payee_id: 'p-transfer', needs_category: false })

  it('does not wear the chip, and reads as a transfer', () => {
    expect(categoryCell(unpaired)).toBe('Transfer')
  })
})

describe('a row a category delete emptied', () => {
  // Provenance, not a category. The row IS uncategorized — `needs_category`
  // is what says so — and the hint only answers "why did this suddenly need
  // filing?", which without it looks like a gap the user forgot about.
  const orphan = txn({
    category_id: null,
    needs_category: true,
    prior_category_id: 'c1',
    prior_category_name: 'Groceries',
  })

  it('still chips as needing a category, and says what it was', () => {
    expect(categoryCell(orphan)).toBe('Needs Categorywas Groceries')
  })

  it('shows no hint on a row that was simply never filed', () => {
    expect(categoryCell(txn({ needs_category: true }))).toBe('Needs Category')
  })

  it('never shows the hint in place of a real category', () => {
    // A move-to delete stamps provenance too, so a filed row can carry it.
    // The cell must render the category it is actually in.
    expect(
      categoryCell(txn({ category_id: 'c1', prior_category_name: 'Old Groceries' }))
    ).toBe('Groceries')
  })
})
