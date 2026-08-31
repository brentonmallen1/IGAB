/**
 * Ceremony only where money is at stake: an empty category deletes on the
 * spot with an undo toast; anything with something to decide — or a preview
 * that will not load — gets the dialog. The plan promised this and review
 * found it unimplemented (`is_empty` was served and read by nobody).
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useDeleteCategoryFlow } from './useDeleteCategoryFlow'
import type { CategoryDeletePreview } from '../../../api/categories'
import { ROOT } from '../../../api/queryKeys'

const deleteMutate = vi.hoisted(() =>
  vi.fn(() => Promise.resolve({ change_id: 'chg-9', category_ids: ['c1'] }))
)
const showUndo = vi.hoisted(() => vi.fn())
let previewResult: () => Promise<CategoryDeletePreview>

vi.mock('../../../api/categories', async () => {
  const actual =
    await vi.importActual<typeof import('../../../api/categories')>('../../../api/categories')
  return {
    ...actual,
    deletePreviewOptions: () => ({
      queryKey: [ROOT.categoryDeletePreview, 'test'],
      queryFn: () => previewResult(),
      staleTime: 0,
      gcTime: 0,
    }),
    useDeleteCategories: () => ({ mutateAsync: deleteMutate, isPending: false }),
  }
})
vi.mock('../../../utils/toastUndo', () => ({ useToastUndoChange: () => showUndo }))
vi.mock('./DeleteCategoryModal', () => ({
  DeleteCategoryModal: () => <div data-testid="delete-dialog" />,
}))

function preview(over: Partial<CategoryDeletePreview> = {}): CategoryDeletePreview {
  return {
    category_ids: ['c1'],
    category_names: ['Empty'],
    transaction_count: 0,
    reconciled_count: 0,
    available: '0',
    future_assigned: '0',
    payee_count: 0,
    scheduled_count: 0,
    references: [],
    may_hard_delete: true,
    moving_activity: '0',
    released_if_moved: '0',
    released_if_uncategorized: '0',
    blocked_by: [],
    is_empty: true,
    ...over,
  }
}

function Harness() {
  const { requestDelete, modal } = useDeleteCategoryFlow('b1')
  return (
    <>
      <button onClick={() => requestDelete({ kind: 'categories', ids: ['c1'], name: 'Empty' })}>
        go
      </button>
      {modal}
    </>
  )
}

function renderFlow() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <Harness />
    </QueryClientProvider>
  )
}

beforeEach(() => {
  deleteMutate.mockClear()
  showUndo.mockClear()
})

describe('useDeleteCategoryFlow', () => {
  it('deletes an empty category on the spot — no dialog, an undo toast', async () => {
    previewResult = () => Promise.resolve(preview())
    renderFlow()
    await userEvent.click(screen.getByText('go'))

    await waitFor(() => expect(deleteMutate).toHaveBeenCalled())
    expect(showUndo).toHaveBeenCalledWith('chg-9', 'Empty deleted')
    expect(screen.queryByTestId('delete-dialog')).not.toBeInTheDocument()
  })

  it('opens the dialog when there is anything to decide', async () => {
    previewResult = () => Promise.resolve(preview({ is_empty: false, transaction_count: 3 }))
    renderFlow()
    await userEvent.click(screen.getByText('go'))

    expect(await screen.findByTestId('delete-dialog')).toBeInTheDocument()
    expect(deleteMutate).not.toHaveBeenCalled()
  })

  it('opens the dialog for a blocked category even when it is empty', async () => {
    // The dialog is where the blocking reason is explained; a one-click 400
    // toast is not an explanation.
    previewResult = () =>
      Promise.resolve(preview({ blocked_by: ["'Visa Payment' is the payment category for Visa."] }))
    renderFlow()
    await userEvent.click(screen.getByText('go'))

    expect(await screen.findByTestId('delete-dialog')).toBeInTheDocument()
    expect(deleteMutate).not.toHaveBeenCalled()
  })

  it('falls through to the dialog when the preview cannot be fetched', async () => {
    previewResult = () => Promise.reject(new Error('offline'))
    renderFlow()
    await userEvent.click(screen.getByText('go'))

    expect(await screen.findByTestId('delete-dialog')).toBeInTheDocument()
    expect(deleteMutate).not.toHaveBeenCalled()
  })
})
