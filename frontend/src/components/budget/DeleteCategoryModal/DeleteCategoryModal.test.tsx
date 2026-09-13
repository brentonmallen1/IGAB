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
    available: 60,
    future_assigned: 50,
    payee_count: 0,
    scheduled_count: 0,
    references: [],
    may_hard_delete: true,
    moving_activity: 40,
    released_if_moved: 110,
    released_if_uncategorized: 110,
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

/** The same dialog opened on a whole group. `useArchiveCategoryGroup` is the
 *  real hook here — nothing in these cases presses the button — but the target
 *  shape is what decides which sentences render. */
function renderGroupModal(over: Partial<CategoryDeletePreview> = {}) {
  preview = makePreview(over)
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <DeleteCategoryModal
        budgetId="b1"
        target={{ kind: 'group', id: 'g1', name: 'Fitness' }}
        month="2026-08-01"
        onClose={vi.fn()}
        onDeleted={vi.fn()}
      />
    </QueryClientProvider>
  )
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
    renderModal({ released_if_moved: 110, released_if_uncategorized: 80 })
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

  it('will not delete until a destination is chosen, and asks for one', async () => {
    renderModal()
    // Move is the default. The button used to sit inert with no reason given;
    // it stays enabled like every dialog's primary and names what is missing.
    const del = screen.getByRole('button', { name: 'Delete' })
    expect(del).toBeEnabled()
    await userEvent.click(del)
    expect(screen.getByRole('alert')).toHaveTextContent(/Choose a category to move/)
    expect(deleteMutate).not.toHaveBeenCalled()
    // Answering the question clears it.
    await userEvent.click(screen.getByRole('radio', { name: /Leave them uncategorized/ }))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
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

/**
 * Why the dialog is naming envelopes that are nowhere on the budget page.
 *
 * The grid draws no archived category, so a group of them looks empty there
 * and full here — and the dialog used to list the names with no explanation,
 * which reads as the app having forgotten that they were moved out. Both
 * figures are served (`archived_count`, `all_archived`); the sentences are the
 * only thing this file adds.
 */
describe('a group whose envelopes are archived', () => {
  it('explains why the group looked empty when every one of them is archived', () => {
    renderGroupModal({
      category_ids: ['c1', 'c2'],
      category_names: ['Coaching', 'Equipment'],
      archived_count: 2,
      all_archived: true,
    })
    expect(screen.getByText(/why the group looks empty on the budget page/i)).toBeInTheDocument()
    expect(screen.getByText('Coaching, Equipment')).toBeInTheDocument()
  })

  it('says how many are hidden when only some of them are', () => {
    renderGroupModal({
      category_ids: ['c1', 'c2', 'c3'],
      category_names: ['Coaching', 'Equipment', 'Classes'],
      archived_count: 1,
      all_archived: false,
    })
    expect(screen.getByText(/1 of the categories below is archived/i)).toBeInTheDocument()
  })

  it('says nothing about archiving on a group with none', () => {
    renderGroupModal({ archived_count: 0, all_archived: false })
    expect(screen.queryByText(/archived/i)).toBeNull()
  })

  it('says nothing about it on a plain category selection either', () => {
    // `archived_count` is a group figure; a multi-select delete of archived
    // envelopes is started from the archived room, where they are on screen.
    renderModal({ archived_count: 2, all_archived: true })
    expect(screen.queryByText(/why the group looks empty/i)).toBeNull()
  })
})

/**
 * The button that had to be offered and then failed.
 *
 * A group whose envelopes were all archived long ago is a heading over nothing
 * on the budget page, and the only way to take it off the page is to archive
 * the group. The server refused that over one of those envelopes' stranded
 * balances — an envelope already off the budget — so this dialog waved the
 * button through its own gate and the press failed at the server. Now the
 * server does not ask the question of an envelope it is not moving, and the
 * gate is the server's answer and nothing else.
 */
describe('archiving a group of already-archived envelopes', () => {
  it('offers the button on the served answer, not a client-side exception', () => {
    archivePreview = {
      may_archive: true,
      blocked_by_balance: [],
      blocked_by_link: [],
      blocked_by_schedule: [],
    }
    renderGroupModal({ archived_count: 2, all_archived: true })
    expect(screen.getByRole('button', { name: 'Archive group instead' })).toBeEnabled()
  })

  it('still refuses when a live envelope in the group holds money', () => {
    archivePreview = {
      may_archive: false,
      blocked_by_balance: ['Dining'],
      blocked_by_link: [],
      blocked_by_schedule: [],
    }
    renderGroupModal({ archived_count: 1, all_archived: false })
    const button = screen.getByRole('button', { name: 'Archive instead' })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('title', 'Cannot archive: Dining')
  })
})
