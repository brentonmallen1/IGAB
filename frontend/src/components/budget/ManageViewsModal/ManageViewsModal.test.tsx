/**
 * Managing views. The list is the only place to reach every view — the bar's
 * selector switches between them but cannot edit or remove one — so what
 * matters here is that each view is listed with working edit and delete, and
 * that deleting the view you are looking at drops you back to the default
 * groups rather than leaving the page pointed at nothing.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { BudgetView } from '../../../types'

const viewsState = vi.hoisted(() => ({ data: [] as BudgetView[] }))
const deleteMutate = vi.hoisted(() => vi.fn().mockResolvedValue(undefined))
const store = vi.hoisted(() => ({
  activeViewId: null as string | null,
  setActiveView: vi.fn(),
  openViewModal: vi.fn(),
}))

vi.mock('../../../api/budgetViews', () => ({
  useBudgetViews: () => viewsState,
  useDeleteBudgetView: () => ({ mutateAsync: deleteMutate, isPending: false }),
}))
vi.mock('../../../stores/uiStore', () => ({
  useUIStore: (sel: (s: typeof store) => unknown) => sel(store),
}))
vi.mock('../../../hooks/useFocusTrap', () => ({ useFocusTrap: () => ({ current: null }) }))

import { ManageViewsModal } from './ManageViewsModal'

function view(id: string, name: string, groups = 2): BudgetView {
  return {
    id,
    budget_id: 'b1',
    name,
    sort_order: 0,
    hide_unassigned: false,
    groups: Array.from({ length: groups }, (_, i) => ({
      id: `${id}-g${i}`,
      name: `G${i}`,
      sort_order: i,
    })),
    placements: [],
    created_at: '',
    updated_at: '',
  }
}

function renderModal() {
  return render(<ManageViewsModal budgetId="b1" onClose={vi.fn()} />)
}

describe('ManageViewsModal', () => {
  beforeEach(() => {
    viewsState.data = []
    store.activeViewId = null
    vi.clearAllMocks()
  })

  it('explains what a view is when there are none', () => {
    renderModal()
    expect(screen.getByText(/No views yet/)).toBeInTheDocument()
  })

  it('lists every view with its group count', () => {
    viewsState.data = [view('v1', 'Need / Want / Save', 3), view('v2', 'By Owner', 1)]
    renderModal()
    expect(screen.getByText('Need / Want / Save')).toBeInTheDocument()
    expect(screen.getByText('3 groups')).toBeInTheDocument()
    expect(screen.getByText('1 group')).toBeInTheDocument()
  })

  it('marks the view currently in use', () => {
    viewsState.data = [view('v1', 'Need / Want / Save'), view('v2', 'By Owner')]
    store.activeViewId = 'v2'
    renderModal()
    expect(screen.getByText(/in use/)).toBeInTheDocument()
  })

  it('edit opens the editor for that view', () => {
    viewsState.data = [view('v1', 'Need / Want / Save')]
    renderModal()
    fireEvent.click(screen.getByLabelText('Edit view Need / Want / Save'))
    expect(store.openViewModal).toHaveBeenCalledWith('v1')
  })

  it('deleting the active view falls back to the default groups', async () => {
    viewsState.data = [view('v1', 'Need / Want / Save')]
    store.activeViewId = 'v1'
    renderModal()
    fireEvent.click(screen.getByLabelText('Delete view Need / Want / Save'))
    await vi.waitFor(() => expect(deleteMutate).toHaveBeenCalledWith('v1'))
    expect(store.setActiveView).toHaveBeenCalledWith(null)
  })

  it('deleting a view you are not looking at leaves the selection alone', async () => {
    viewsState.data = [view('v1', 'A'), view('v2', 'B')]
    store.activeViewId = 'v1'
    renderModal()
    fireEvent.click(screen.getByLabelText('Delete view B'))
    await vi.waitFor(() => expect(deleteMutate).toHaveBeenCalledWith('v2'))
    expect(store.setActiveView).not.toHaveBeenCalled()
  })
})
