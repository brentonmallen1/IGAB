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
let names: Record<string, string> = {}

vi.mock('../../api/changes', () => ({
  useChanges: () => ({
    data: { changes, total: changes.length, names },
    isLoading: false,
    error: null,
  }),
  useUndoChange: () => ({ mutateAsync: undoChange, isPending: false }),
  useUndoBatch: () => ({ mutateAsync: undoBatch, isPending: false }),
  useUndoNewer: () => ({ mutateAsync: undoNewer, isPending: false }),
  invalidateAfterUndo: vi.fn(),
  changesKeys: { budget: (id: string) => ['changes', id] },
}))
const redo = vi.hoisted(() => vi.fn())
vi.mock('../../hooks/useUndoRedo', () => ({
  useUndoRedo: () => ({ undo: vi.fn(), redo, enabled: true }),
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
    seq: 0,
    undo_seq: null,
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
  names = {}
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
    changes = [change('a', { batch_id: 'batch-1' }), change('b', { batch_id: 'batch-1' })]
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

  it('offers Redo only on the redo head, and not under a newer live change', async () => {
    const at = '2026-09-01T10:00:00+00:00'
    // B (seq 9) was undone after C (seq 10): B is the head.
    changes = [
      change('c', { seq: 10, undo_seq: 1, undone_at: at }),
      change('b', { seq: 9, undo_seq: 2, undone_at: at }),
    ]
    render(<ActivityPage />)
    expect(screen.getAllByTitle('Redo this change')).toHaveLength(1)
    await userEvent.click(screen.getByTitle('Redo this change'))
    expect(redo).toHaveBeenCalled()
  })

  it('offers no Redo while a live change is newer than the last undo', () => {
    changes = [
      change('live', { seq: 11 }),
      change('c', { seq: 10, undo_seq: 1, undone_at: '2026-09-01T10:00:00+00:00' }),
    ]
    render(<ActivityPage />)
    expect(screen.queryByTitle('Redo this change')).toBeNull()
  })

  it('names the payee on the summary line, and expands to a before → after diff', async () => {
    // The server resolves ids to names beside the page; the card shows them
    // instead of UUIDs, and tapping the row reveals what actually moved.
    names = { p1: 'Harborstone Market' }
    changes = [
      change('a', {
        action: 'update',
        before: { amount: '-42.50', payee_id: 'p1' },
        after: { amount: '-60.00', payee_id: 'p1' },
      }),
    ]
    render(<ActivityPage />)

    expect(screen.queryByText('-$42.50')).toBeNull() // detail hidden until asked
    await userEvent.click(screen.getByText('Amount → -$60.00 · Harborstone Market'))
    expect(screen.getByText('-$42.50')).toBeInTheDocument()
    expect(screen.getByText('-$60.00')).toBeInTheDocument()
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
