import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ArchivedCategoriesModal } from './ArchivedCategoriesModal'

const unarchive = vi.fn()
const unarchiveGroup = vi.fn()
let rows: unknown[] = []

vi.mock('../../../api/categories', () => ({
  useArchivedCategories: () => ({ data: rows, isLoading: false }),
  useUnarchiveCategories: () => ({ mutate: unarchive }),
  useUnarchiveCategoryGroup: () => ({ mutate: unarchiveGroup }),
}))

function row(over: Record<string, unknown> = {}) {
  return {
    id: 'c1',
    name: 'Gym',
    group_id: 'g1',
    group_name: 'Everyday',
    transaction_count: 12,
    archived_at: '2026-08-01T00:00:00Z',
    available: 0.0,
    group_is_archived: false,
    ...over,
  }
}

function show() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ArchivedCategoriesModal
        budgetId="b1"
        month="2026-08-01"
        onClose={() => {}}
        onDelete={vi.fn()}
      />
    </QueryClientProvider>
  )
}

beforeEach(() => {
  unarchive.mockClear()
  unarchiveGroup.mockClear()
})

describe('ArchivedCategoriesModal', () => {
  it('shows the three facts that decide an envelope’s fate', () => {
    rows = [row()]
    show()
    expect(screen.getByText('Gym')).toBeInTheDocument()
    expect(screen.getByText('Everyday')).toBeInTheDocument()
    expect(screen.getByText('12 transactions')).toBeInTheDocument()
    // Not asserting the rendered date itself: it is locale- and
    // timezone-dependent, and pinning it here would make this test fail
    // on a machine set differently rather than on a real regression.
    expect(screen.getByText(/^Archived \d|^Archived [A-Z]/)).toBeInTheDocument()
  })

  it('says so plainly when a row predates the archived-on column', () => {
    // `updated_at` would have been wrong — any edit bumps it — so the column
    // is NULL for older rows and the UI must not invent a date.
    rows = [row({ archived_at: null })]
    show()
    expect(screen.getByText('Archived before dates were kept')).toBeInTheDocument()
  })

  it('surfaces money left in an envelope the budget no longer draws', () => {
    // The whole reason `available` is on this row. These predate the archive
    // flow, which now refuses to leave money behind.
    rows = [row({ available: '75.00' })]
    show()
    expect(screen.getByText(/Gym still holds money/)).toBeInTheDocument()
    expect(screen.getByText(/left in it/)).toBeInTheDocument()
  })

  it('stays quiet when nothing holds money', () => {
    rows = [row()]
    show()
    expect(screen.queryByText(/still holds money/)).not.toBeInTheDocument()
  })

  it('restores the row it was clicked on', async () => {
    rows = [row()]
    show()
    await userEvent.click(screen.getByRole('button', { name: /Restore/ }))
    expect(unarchive).toHaveBeenCalledWith({ ids: ['c1'], month: '2026-08-01' })
  })

  it('restores the group when the group is what archived the row', async () => {
    // The row is listed because its *group* is archived; its own flag is
    // false, so clearing that again is a button that does nothing. The client
    // cannot work this out alone — archived groups are absent from the groups
    // listing it holds — so the server says which case this is.
    rows = [row({ group_is_archived: true })]
    show()
    await userEvent.click(screen.getByRole('button', { name: /Restore group/ }))
    expect(unarchiveGroup).toHaveBeenCalledWith({ id: 'g1', month: '2026-08-01' })
    expect(unarchive).not.toHaveBeenCalled()
  })

  it('says the group is what comes back, rather than promising one envelope', () => {
    rows = [row({ group_is_archived: true })]
    show()
    expect(screen.getByRole('button', { name: /Restore group/ })).toHaveAttribute(
      'title',
      expect.stringContaining('Everyday')
    )
  })

  it('explains itself when there is nothing archived', () => {
    rows = []
    show()
    expect(screen.getByText(/Nothing archived/)).toBeInTheDocument()
  })
})
