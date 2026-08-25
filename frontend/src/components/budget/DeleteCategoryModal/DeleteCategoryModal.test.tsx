/**
 * The dialog's whole job is to be honest about what is about to happen.
 *
 * It replaced three copies of a one-line confirm that all said "Transactions
 * will lose their category" — a sentence that was false at the time, because
 * the old delete flipped a flag and left every transaction pointing at the
 * dead category. So these tests are mostly about the numbers being shown and
 * the choice being real, not about markup.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DeleteCategoryModal } from './DeleteCategoryModal'
import type { CategoryDeletePreview } from '../../../api/categories'

const deleteMutate = vi.hoisted(() =>
  vi.fn((_vars: { target: unknown; moveTo: string | null; month: string }) =>
    Promise.resolve({ change_id: 'chg-1', category_ids: ['c1'] })
  )
)
let preview: CategoryDeletePreview

vi.mock('../../../api/categories', async () => {
  const actual = await vi.importActual<typeof import('../../../api/categories')>(
    '../../../api/categories'
  )
  return {
    ...actual,
    useCategoryDeletePreview: () => ({ data: preview, isLoading: false }),
    useCategories: () => ({
      data: [
        { id: 'c1', name: 'Groceries', category_group_id: 'g1', is_categorizable: true },
        { id: 'c2', name: 'Dining', category_group_id: 'g1', is_categorizable: true },
        { id: 'c3', name: 'Visa Payment', category_group_id: 'g1', is_categorizable: false },
      ],
    }),
    useCategoryGroups: () => ({ data: [{ id: 'g1', name: 'Everyday' }] }),
    useDeleteCategories: () => ({ mutateAsync: deleteMutate, isPending: false }),
  }
})

function makePreview(over: Partial<CategoryDeletePreview> = {}): CategoryDeletePreview {
  return {
    category_ids: ['c1'],
    category_names: ['Groceries'],
    transaction_count: 412,
    reconciled_count: 0,
    available: '60.0000',
    future_assigned: '50.0000',
    payee_count: 0,
    scheduled_count: 0,
    blocked_by: [],
    is_empty: false,
    ...over,
  }
}

function renderModal(over: Partial<CategoryDeletePreview> = {}) {
  preview = makePreview(over)
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const onDeleted = vi.fn()
  render(
    <QueryClientProvider client={qc}>
      <DeleteCategoryModal
        budgetId="b1"
        target={{ kind: 'categories', ids: ['c1'], name: 'Groceries' }}
        month="2026-08-01"
        onClose={vi.fn()}
        onDeleted={onDeleted}
      />
    </QueryClientProvider>
  )
  return { onDeleted }
}

beforeEach(() => {
  deleteMutate.mockClear()
})

describe('DeleteCategoryModal', () => {
  it('states what is about to move before the user commits', () => {
    renderModal()
    expect(screen.getByText('412')).toBeInTheDocument()
    // available + future_assigned, from the server. The dialog never adds up
    // money of its own — a differential test on the server holds these to what
    // the delete then does.
    expect(screen.getByText('$110.00')).toBeInTheDocument()
  })

  it('calls out reconciled rows, which cannot be re-filed by hand afterwards', () => {
    renderModal({ reconciled_count: 118 })
    expect(screen.getByText(/118 reconciled/)).toBeInTheDocument()
  })

  it('offers a real choice about the transactions', () => {
    renderModal()
    expect(screen.getByRole('radio', { name: /Move them to another category/ })).toBeChecked()
    expect(screen.getByRole('radio', { name: /Leave them uncategorized/ })).toBeInTheDocument()
  })

  it('will not delete until a destination is chosen', () => {
    renderModal()
    // Move is the default, so the button stays inert until the picker answers.
    expect(screen.getByRole('button', { name: 'Delete' })).toBeDisabled()
  })

  it('uncategorizing needs no destination', async () => {
    renderModal()
    await userEvent.click(screen.getByRole('radio', { name: /Leave them uncategorized/ }))
    expect(screen.getByRole('button', { name: 'Delete' })).toBeEnabled()
  })

  it('sends move_to as null when uncategorizing', async () => {
    const { onDeleted } = renderModal()
    await userEvent.click(screen.getByRole('radio', { name: /Leave them uncategorized/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(deleteMutate).toHaveBeenCalled())
    expect(deleteMutate.mock.calls[0][0]).toMatchObject({ moveTo: null, month: '2026-08-01' })
    // The change id is what makes the undo toast possible.
    expect(onDeleted).toHaveBeenCalledWith('chg-1')
  })

  it('refuses outright when the category is load-bearing, and says why', () => {
    renderModal({
      blocked_by: ["'Visa Payment' is the payment category for Visa. Delete or unlink that account first."],
    })
    expect(screen.getByRole('alert')).toHaveTextContent(/payment category for Visa/)
    expect(screen.getByRole('button', { name: 'Delete' })).toBeDisabled()
  })

  it('mentions hiding, which keeps the history and the money', () => {
    renderModal()
    expect(screen.getByText(/hidden categories keep their history/i)).toBeInTheDocument()
  })

  it('skips the transaction choice when there is nothing filed there', () => {
    renderModal({ transaction_count: 0 })
    expect(screen.queryByRole('radio')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete' })).toBeEnabled()
  })
})
