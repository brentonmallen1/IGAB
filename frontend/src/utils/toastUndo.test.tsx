import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { act, render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import toast, { Toaster } from 'react-hot-toast'
import { HEAD_MOVED_MESSAGE, UNDOABLE_TOAST_ID, useUndoToast } from './toastUndo'
import { useAppStore } from '../stores/appStore'

const api = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn() }))
vi.mock('../api/client', () => ({ apiClient: api }))

function Harness({ onReady }: { onReady: (notify: ReturnType<typeof useUndoToast>) => void }) {
  const notify = useUndoToast('acc-1')
  onReady(notify)
  return null
}

function mount() {
  const qc = new QueryClient()
  let notify!: ReturnType<typeof useUndoToast>
  render(
    <QueryClientProvider client={qc}>
      <Toaster />
      <Harness onReady={(n) => (notify = n)} />
    </QueryClientProvider>
  )
  return { notify, qc }
}

describe('useUndoToast', () => {
  beforeEach(() => {
    useAppStore.setState({ currentBudgetId: 'b1' })
    api.post.mockReset()
    api.get.mockReset()
    api.post.mockResolvedValue({ data: { undone_change_ids: ['c1'], skipped_change_ids: [] } })
  })

  afterEach(() => {
    act(() => toast.remove())
  })

  it('is a plain success toast with no target', async () => {
    const { notify } = mount()
    act(() => notify('Saved'))
    expect(await screen.findByText('Saved')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Undo' })).toBeNull()
  })

  it('posts the batch endpoint for a batch target', async () => {
    const { notify } = mount()
    act(() => notify('Transaction deleted', { batch: 'bt-7' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Undo' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/b1/changes/batch/bt-7/undo'))
    expect(await screen.findByText('Undone')).toBeInTheDocument()
  })

  it('posts the change endpoint for a change target', async () => {
    const { notify } = mount()
    act(() => notify('Groceries deleted', { change: 'ch-2' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Undo' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/b1/changes/ch-2/undo'))
  })

  it('undoes the latest change only while the log head has not moved', async () => {
    // Head 41 when shown, still 41 when tapped → the delete it names is
    // still the newest thing, so undo it.
    api.get.mockResolvedValue({ data: { changes: [{ seq: 41 }], total: 1, names: {} } })
    const { notify } = mount()
    act(() => notify('Assigned $40 to Groceries', 'latest'))
    fireEvent.click(await screen.findByRole('button', { name: 'Undo' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/b1/changes/undo'))
  })

  it('declines when something has landed since, instead of undoing that', async () => {
    // Shown at head 41; an inline memo edit lands (head 42) before the tap.
    // Undoing "the latest" would take back the memo, not the delete.
    api.get
      .mockResolvedValueOnce({ data: { changes: [{ seq: 41 }], total: 1, names: {} } })
      .mockResolvedValueOnce({ data: { changes: [{ seq: 42 }], total: 1, names: {} } })
    const { notify } = mount()
    act(() => notify('Transaction deleted', 'latest'))
    fireEvent.click(await screen.findByRole('button', { name: 'Undo' }))
    expect(await screen.findByText(HEAD_MOVED_MESSAGE)).toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('carries rich content beside the same Undo', async () => {
    // The quick-add's envelope figure is an element, not a sentence; it must
    // not need a second toast helper to keep its Undo.
    api.get.mockResolvedValue({ data: { changes: [{ seq: 7 }], total: 1, names: {} } })
    const { notify } = mount()
    act(() =>
      notify(
        <span>
          Groceries <b>$198.00</b>
        </span>,
        'latest'
      )
    )
    expect(await screen.findByText('$198.00')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/b1/changes/undo'))
  })

  it('replaces an older undoable toast so a stale Undo never lingers', async () => {
    const { notify } = mount()
    act(() => notify('First', { batch: 'a' }))
    expect(await screen.findByText('First')).toBeInTheDocument()
    act(() => notify('Second', { batch: 'b' }))
    expect(await screen.findByText('Second')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText('First')).toBeNull())
    expect(screen.getAllByRole('button', { name: 'Undo' })).toHaveLength(1)
    expect(UNDOABLE_TOAST_ID).toBe('undoable')
  })

  it("reports the server's conflict sentence when the undo is refused", async () => {
    api.post.mockRejectedValue({
      response: { data: { detail: { message: 'Newer changes touch this transaction' } } },
    })
    const { notify } = mount()
    act(() => notify('Transaction deleted', { batch: 'bt-1' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Undo' }))
    expect(await screen.findByText('Newer changes touch this transaction')).toBeInTheDocument()
  })
})
