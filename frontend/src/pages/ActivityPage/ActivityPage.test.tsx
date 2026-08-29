/**
 * Two properties of the activity list.
 *
 * A batch is one thing that happened, so it reads as one line — a bulk assign
 * of forty categories used to render forty cards and bury the rest of the day.
 *
 * And "revert to here" rests BETWEEN two entries. The id it sends is the
 * newest entry BELOW the line, so everything above goes and everything below
 * stays; there is no inclusive-or-not question to answer. The count in the
 * prompt comes from a dry run of the same query that does the work.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ActivityPage } from './ActivityPage'
import type { Change } from '../../api/changes'

const undoNewer = vi.hoisted(() =>
  vi.fn((_args: { changeId: string; dryRun?: boolean; force?: boolean }) =>
    Promise.resolve({ undone_change_ids: ['x', 'y'] })
  )
)
const undoBatch = vi.hoisted(() =>
  vi.fn((_args: { batchId: string }) => Promise.resolve({ undone_change_ids: ['x', 'y', 'z'] }))
)
const undoChange = vi.hoisted(() =>
  vi.fn((_args: { changeId: string }) => Promise.resolve({ undone_change_ids: ['x'] }))
)
let changes: Change[] = []

vi.mock('../../api/changes', () => ({
  useChanges: () => ({ data: { changes, total: changes.length }, isLoading: false, error: null }),
  useUndoChange: () => ({ mutateAsync: undoChange, isPending: false }),
  useUndoBatch: () => ({ mutateAsync: undoBatch, isPending: false }),
  useUndoNewer: () => ({ mutateAsync: undoNewer, isPending: false }),
  invalidateAfterUndo: vi.fn(),
}))
vi.mock('@tanstack/react-query', () => ({ useQueryClient: () => ({}) }))
vi.mock('../../stores/appStore', () => ({
  useAppStore: (sel: (s: { currentBudgetId: string }) => unknown) => sel({ currentBudgetId: 'b1' }),
}))
vi.mock('../../hooks/useFormatters', () => ({
  useFormatters: () => ({ formatDateTime: (d: string) => d }),
}))
vi.mock('react-hot-toast', () => ({
  default: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}))
const confirmAsync = vi.hoisted(() => vi.fn(() => Promise.resolve(true)))
vi.mock('../../stores/confirmStore', () => ({ confirmAsync }))

function change(id: string, over: Partial<Change> = {}): Change {
  return {
    id,
    entity_type: 'transaction',
    entity_id: `e-${id}`,
    action: 'create',
    before: null,
    after: null,
    batch_id: null,
    source: 'manual',
    undone_at: null,
    created_at: '2026-08-27T13:53:41+00:00',
    user_id: null,
    user_display_name: null,
    ...over,
  }
}

beforeEach(() => {
  undoNewer.mockClear()
  undoBatch.mockClear()
  undoChange.mockClear()
  confirmAsync.mockClear()
})

describe('ActivityPage', () => {
  it('collapses a batch to one line, and expands it on request', async () => {
    changes = [
      change('a', { batch_id: 'b', action: 'update', entity_type: 'assignment' }),
      change('b', { batch_id: 'b', action: 'update', entity_type: 'assignment' }),
      change('c', { batch_id: 'b', action: 'update', entity_type: 'assignment' }),
    ]
    render(<ActivityPage />)

    expect(screen.getByText('Updated 3 assignments')).toBeInTheDocument()
    expect(screen.queryAllByText('Updated assignment')).toHaveLength(0)

    await userEvent.click(screen.getByText('Updated 3 assignments'))
    expect(screen.getAllByText('Updated assignment')).toHaveLength(3)
  })

  it('undoes a whole batch from its one line', async () => {
    changes = [
      change('a', { batch_id: 'batch-1' }),
      change('b', { batch_id: 'batch-1' }),
    ]
    render(<ActivityPage />)

    await userEvent.click(screen.getByTitle('Undo this whole batch'))
    expect(undoBatch).toHaveBeenCalledWith({ batchId: 'batch-1' })
  })

  it('reverts to the entry below the line, counting with a dry run first', async () => {
    // newest first, as the API returns them
    changes = [change('newest'), change('middle'), change('oldest')]
    render(<ActivityPage />)

    const lines = screen.getAllByTitle('Undo everything above this line')
    expect(lines).toHaveLength(2) // between three entries, never below the last

    await userEvent.click(lines[0]) // the line under "newest"

    // asked what would go, with the id of the entry BELOW the line…
    expect(undoNewer).toHaveBeenNthCalledWith(1, { changeId: 'middle', dryRun: true })
    // …said how many in the prompt…
    expect(confirmAsync).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Undo the 2 changes above this line?' })
    )
    // …then did it, with the same anchor
    expect(undoNewer).toHaveBeenNthCalledWith(2, { changeId: 'middle' })
  })

  it('does nothing when the confirmation is declined', async () => {
    changes = [change('newest'), change('older')]
    confirmAsync.mockResolvedValueOnce(false)
    render(<ActivityPage />)

    await userEvent.click(screen.getByTitle('Undo everything above this line'))

    expect(undoNewer).toHaveBeenCalledTimes(1)
    expect(undoNewer).toHaveBeenCalledWith({ changeId: 'older', dryRun: true })
  })
})
