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
let previewFailed = false
/** The archive endpoint's own answer. The dialog gates "Archive instead" on
 *  this and not on the delete preview's `blocked_by`: the two refuse on
 *  different grounds, so reading the delete's answer offered the button on an
 *  envelope the archive would then refuse over its balance. */
let archivePreview: {
  may_archive: boolean
  blocked_by_balance: string[]
  blocked_by_link: string[]
  blocked_by_schedule: string[]
}
const refetchSpy = vi.hoisted(() => vi.fn())

vi.mock('../../../api/categories', async () => {
  const actual =
    await vi.importActual<typeof import('../../../api/categories')>('../../../api/categories')
  return {
    ...actual,
    useCategoryDeletePreview: () => ({
      data: preview,
      isLoading: false,
      isError: previewFailed,
      refetch: refetchSpy,
    }),
    useArchivePreview: () => ({ data: archivePreview, isLoading: false, isError: false }),
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
    references: [],
    may_hard_delete: true,
    moving_activity: '40.0000',
    released_if_moved: '110.0000',
    released_if_uncategorized: '110.0000',
    blocked_by: [],
    is_empty: false,
    ...over,
  }
}

/** The preview request failed: no data, isError set — the modal must say so
 *  rather than sit silent with a forever-disabled Delete. */
function renderFailed() {
  previewFailed = true
  preview = undefined as unknown as CategoryDeletePreview
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <DeleteCategoryModal
        budgetId="b1"
        target={{ kind: 'categories', ids: ['c1'], name: 'Groceries' }}
        month="2026-08-01"
        onClose={vi.fn()}
        onDeleted={vi.fn()}
      />
    </QueryClientProvider>
  )
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
  refetchSpy.mockClear()
  previewFailed = false
  archivePreview = {
    may_archive: true,
    blocked_by_balance: [],
    blocked_by_link: [],
    blocked_by_schedule: [],
  }
})

describe('DeleteCategoryModal', () => {
  it('states what is about to move before the user commits', () => {
    renderModal()
    expect(screen.getByText('412')).toBeInTheDocument()
    // Served, from the server. The dialog never adds up money of its own — a
    // differential test on the server holds these to what the delete does.
    expect(screen.getByText('$110.00')).toBeInTheDocument()
    // The spending that moves is stated too.
    expect(screen.getByText('$40.00')).toBeInTheDocument()
  })

  it('shows the figure for the mode the user has selected', async () => {
    // They differ when future-dated activity moves; the dialog must follow
    // the selection rather than quote one number for both.
    renderModal({ released_if_moved: '110.0000', released_if_uncategorized: '80.0000' })
    expect(screen.getByText('$110.00')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('radio', { name: /Leave them uncategorized/ }))
    expect(screen.getByText('$80.00')).toBeInTheDocument()
    expect(screen.queryByText('$110.00')).not.toBeInTheDocument()
  })

  it('says the destination is held harmless', () => {
    renderModal()
    expect(screen.getByText(/balance is not\s+affected/)).toBeInTheDocument()
  })

  it('says so when the preview cannot be loaded, and offers a retry', async () => {
    renderFailed()
    expect(screen.getByRole('alert')).toHaveTextContent(/nothing was deleted/i)
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(refetchSpy).toHaveBeenCalled()
    // No numbers to stand behind, so no Delete.
    expect(screen.getByRole('button', { name: 'Delete' })).toBeDisabled()
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
      blocked_by: [
        "'Visa Payment' is the payment category for Visa. Delete or unlink that account first.",
      ],
    })
    expect(screen.getByRole('alert')).toHaveTextContent(/payment category for Visa/)
    expect(screen.getByRole('button', { name: 'Delete' })).toBeDisabled()
  })

  it('offers archiving as a real choice, not as prose', () => {
    // It used to say "you can hide it instead" in a paragraph, which is advice
    // the user then had to go and act on somewhere else. Archiving is the
    // non-destructive way out of this dialog, so it is a button in it.
    renderModal()
    expect(screen.getByRole('button', { name: /Archive instead/i })).toBeEnabled()
  })

  it('gates Archive on the archive endpoint, not on the delete preview', () => {
    // The delete may proceed — its own `blocked_by` is empty, because a
    // balance is something delete moves rather than refuses over. Archiving
    // refuses, and this button used to read the wrong one of the two and
    // present itself as available.
    archivePreview = {
      may_archive: false,
      blocked_by_balance: ['Groceries'],
      blocked_by_link: [],
      blocked_by_schedule: [],
    }
    // No transactions, so the Delete button is not held back by the
    // destination picker — the only thing left that could disable it is the
    // block, and the delete is not blocked.
    renderModal({ blocked_by: [], transaction_count: 0 })
    expect(screen.getByRole('button', { name: 'Delete' })).toBeEnabled()
    const archive = screen.getByRole('button', { name: /Archive instead/i })
    expect(archive).toBeDisabled()
    // And says which envelope stopped it, rather than being inert in silence.
    expect(archive).toHaveAttribute('title', expect.stringContaining('Groceries'))
  })

  it('names a blocking schedule too', () => {
    archivePreview = {
      may_archive: false,
      blocked_by_balance: [],
      blocked_by_link: [],
      blocked_by_schedule: ['Groceries'],
    }
    renderModal()
    expect(screen.getByRole('button', { name: /Archive instead/i })).toHaveAttribute(
      'title',
      expect.stringContaining('Groceries')
    )
  })

  it('says whether the row itself is about to go', () => {
    // `may_hard_delete` is served precisely so the wording and the behaviour
    // cannot disagree about which of the two deletes is about to happen.
    renderModal()
    expect(screen.getByText(/the category itself is removed/i)).toBeInTheDocument()
  })

  it('names what else points at the category', () => {
    renderModal({
      may_hard_delete: false,
      references: [
        { kind: 'target', label: '1 savings target', count: 1, clearable: true },
        { kind: 'budget_move', label: '2 recorded money moves', count: 2, clearable: false },
      ],
    })
    expect(screen.getByText(/1 savings target/)).toBeInTheDocument()
    // The blocking one says why the row survives, rather than being severed
    // quietly the way a CASCADE would have done it.
    expect(screen.getByText(/2 recorded money moves/)).toBeInTheDocument()
    expect(screen.getByText(/kept as deleted history/i)).toBeInTheDocument()
  })

  it('skips the transaction choice when there is nothing filed there', () => {
    renderModal({ transaction_count: 0 })
    expect(screen.queryByRole('radio')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete' })).toBeEnabled()
  })
})
