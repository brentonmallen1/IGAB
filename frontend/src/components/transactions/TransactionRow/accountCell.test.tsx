/**
 * The account cell in the all-accounts register.
 *
 * The report: "in the all accounts view, I can't seem to edit the account on
 * a transaction inline." You couldn't — every other column there opened an
 * editor on click and this one was plain text, so the only way to move a row
 * was to open the editor. Which is the surface most likely to want it: the
 * all-accounts register is where you notice a receipt landed on the wrong
 * card, because it is the only view that shows you both.
 *
 * Whether a row MAY move is `accountMove.ts`'s rule, shared with the editor's
 * Account field — these tests check that the register asks it and honours the
 * answer, not that it re-derives it.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TransactionRow } from './TransactionRow'
import { useTransactionEditStore } from '../../../stores/transactionEditStore'
import type { Account, Transaction } from '../../../types'

const update = vi.hoisted(() => ({ mutate: vi.fn() }))

vi.mock('../../../api/transactions', () => ({
  useUpdateTransaction: () => ({ mutate: update.mutate, mutateAsync: vi.fn(), isPending: false }),
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
vi.mock('../../../hooks/useMediaQuery', () => ({ useIsMobile: () => false }))

const ACCOUNTS = [
  { id: 'a1', name: 'Harborstone Checking', on_budget: true, is_closed: false },
  { id: 'a2', name: 'Sapphire Visa', on_budget: true, is_closed: false },
  { id: 'a3', name: 'Cascade Point HYSA', on_budget: false, is_closed: false },
] as unknown as Account[]

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
    sync_id: null,
    has_sync_source: false,
    needs_category: false,
    ...overrides,
  } as unknown as Transaction
}

/** `accountLabel` null is a single account's register — no column at all.
 *  A string is the all-accounts register. (Null rather than undefined: a
 *  default parameter would swallow an explicit undefined.) */
function renderRow(t: Transaction, accountLabel: string | null = 'Harborstone Checking') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <TransactionRow
          transaction={t}
          onEdit={vi.fn()}
          payeeMap={new Map()}
          accountMap={new Map(ACCOUNTS.map((a) => [a.id, a.name]))}
          categoryMap={new Map()}
          payees={[]}
          accounts={ACCOUNTS}
          categories={[]}
          categoryGroups={[]}
          isSelected={false}
          orderedIds={[t.id]}
          onSelect={vi.fn()}
          onStartSplit={vi.fn()}
          onDuplicate={vi.fn()}
          onMakeRepeating={vi.fn()}
          accountLabel={accountLabel ?? undefined}
        />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

function accountCell(container: HTMLElement) {
  return container.querySelector('.txn-col--account') as HTMLElement
}

beforeEach(() => {
  update.mutate.mockClear()
  // The edit store is module state: a cell left open by one test renders the
  // next test's row (same id) already in edit mode.
  useTransactionEditStore.setState({ editingField: null, splitEditing: null })
})

describe('the account cell', () => {
  it('opens a picker on click, like every other column here', () => {
    const { container } = renderRow(txn())
    fireEvent.click(accountCell(container))
    expect(screen.getByPlaceholderText('Move to account…')).toBeInTheDocument()
  })

  it('moves the row to the account picked', () => {
    const { container } = renderRow(txn())
    fireEvent.click(accountCell(container))
    // The list commits on mouseDown, before the input's blur can close it.
    fireEvent.mouseDown(screen.getByRole('option', { name: 'Sapphire Visa' }))
    expect(update.mutate).toHaveBeenCalledWith(
      expect.objectContaining({ id: 't1', account_id: 'a2' }),
      expect.anything()
    )
  })

  it('writes nothing when the row is already in the account picked', () => {
    // The server drops a no-op account_id anyway; not sending it keeps a
    // pointless change-log row out of ⌘Z's way.
    const { container } = renderRow(txn())
    fireEvent.click(accountCell(container))
    fireEvent.mouseDown(screen.getByRole('option', { name: 'Harborstone Checking' }))
    expect(update.mutate).not.toHaveBeenCalled()
  })

  it('offers tracking accounts too, under their own heading', () => {
    // A row can legitimately move to a tracking account — the server refuses
    // only if it is carrying a category, and says so.
    const { container } = renderRow(txn())
    fireEvent.click(accountCell(container))
    expect(screen.getByRole('option', { name: 'Cascade Point HYSA' })).toBeInTheDocument()
    expect(screen.getByText('Tracking')).toBeInTheDocument()
  })

  it('stays plain text on a bank-fed row, and says why', () => {
    const { container } = renderRow(txn({ sync_id: 'sf-1' }))
    const cell = accountCell(container)
    expect(cell.title).toMatch(/bank feed decides/)
    fireEvent.click(cell)
    expect(screen.queryByPlaceholderText('Move to account…')).not.toBeInTheDocument()
  })

  it('stays plain text on a reconciled row, and says why', () => {
    const { container } = renderRow(txn({ cleared: 'reconciled' }))
    const cell = accountCell(container)
    expect(cell.title).toMatch(/Reconciled/)
    fireEvent.click(cell)
    expect(screen.queryByPlaceholderText('Move to account…')).not.toBeInTheDocument()
  })

  it('is not drawn at all in a single account’s register', () => {
    const { container } = renderRow(txn(), null)
    expect(accountCell(container)).toBeNull()
  })
})
