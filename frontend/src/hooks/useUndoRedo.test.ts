/**
 * The reported bug, by name: inline-edit a memo, delete a different
 * transaction, press ⌘Z — the DELETE must revert, not the stale memo edit.
 *
 * The old hook kept a client-side shadow stack of inline edits and preferred
 * it unconditionally, so ⌘Z popped whatever the register had pushed last,
 * however long ago. The fix is structural: the shadow stack is gone (there is
 * no historyStore module to consult), and undo asks the server to take back
 * the newest live manual change — so what gets undone is decided by the one
 * ordered log, not by which code path pushed last.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useUndoRedo } from './useUndoRedo'

const post = vi.hoisted(() => vi.fn())
vi.mock('../api/client', () => ({ apiClient: { post } }))

const invalidateAfterUndo = vi.hoisted(() => vi.fn())
vi.mock('../api/changes', () => ({
  invalidateAfterUndo,
  changesKeys: { budget: (id: string) => ['changes', id] },
}))

const invalidateQueries = vi.hoisted(() => vi.fn())
vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries }),
}))

vi.mock('../stores/appStore', () => ({
  useAppStore: (sel: (s: { currentBudgetId: string | null }) => unknown) =>
    sel({ currentBudgetId: 'b1' }),
}))

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }))
vi.mock('react-hot-toast', () => ({ default: toast }))

beforeEach(() => {
  post.mockReset()
  toast.mockClear()
  toast.success.mockClear()
  invalidateAfterUndo.mockClear()
  invalidateQueries.mockClear()
})

describe('useUndoRedo', () => {
  it('undoes by asking the server for the newest manual change — no local stack', async () => {
    // The server picked the delete (the newest manual change), whatever
    // inline edits happened before it.
    post.mockResolvedValueOnce({
      data: { undone_change_ids: ['d1', 'd2'], action: 'delete', entity_type: 'transaction' },
    })
    const { result } = renderHook(() => useUndoRedo())

    await act(() => result.current.undo())

    expect(post).toHaveBeenCalledExactlyOnceWith('/b1/changes/undo')
    expect(invalidateAfterUndo).toHaveBeenCalledWith(expect.anything(), 'b1')
    expect(toast.success).toHaveBeenCalledWith(
      'Undid: deleted transaction — and the other 1 in that batch'
    )
  })

  it('relays the server refusal when there is nothing to undo', async () => {
    post.mockRejectedValueOnce({
      response: { data: { detail: { message: 'Nothing to undo' } } },
    })
    const { result } = renderHook(() => useUndoRedo())

    await act(() => result.current.undo())

    expect(toast).toHaveBeenCalledWith('Nothing to undo')
    expect(invalidateAfterUndo).not.toHaveBeenCalled()
  })

  it('redoes through the server and relays its refusal', async () => {
    post.mockResolvedValueOnce({ data: { undone_change_ids: ['x'] } })
    const { result } = renderHook(() => useUndoRedo())
    await act(() => result.current.redo())
    expect(post).toHaveBeenCalledExactlyOnceWith('/b1/changes/redo')
    expect(toast.success).toHaveBeenCalledWith('Redone')

    post.mockRejectedValueOnce({
      response: { data: { detail: { message: 'Nothing to redo — something changed' } } },
    })
    await act(() => result.current.redo())
    expect(toast).toHaveBeenCalledWith('Nothing to redo — something changed')
  })
})
