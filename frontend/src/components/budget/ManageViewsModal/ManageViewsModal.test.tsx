/**
 * Managing views. The list is the only place to reach every view — the bar's
 * selector switches between them but cannot edit or remove one — so what
 * matters here is that each view is listed with working edit and delete, and
 * that deleting the view you are looking at drops you back to the default
 * groups rather than leaving the page pointed at nothing.
 *
 * The uiStore here is REAL, deliberately. This modal and the view editor share
 * one modal slot: "New View" swaps the slot to the editor, and the page's
 * onClose is closeModal. A mocked store let `openModal(...); onClose()` pass —
 * two calls, both "correct" — while the real store saw the second call null
 * the slot the first had just filled, so nothing ever rendered.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { BudgetView } from '../../../types'

const viewsState = vi.hoisted(() => ({ data: [] as BudgetView[] }))
const deleteMutate = vi.hoisted(() => vi.fn().mockResolvedValue(undefined))
const confirmAsync = vi.hoisted(() => vi.fn().mockResolvedValue(true))

vi.mock('../../../api/budgetViews', () => ({
  useBudgetViews: () => viewsState,
  useDeleteBudgetView: () => ({ mutateAsync: deleteMutate, isPending: false }),
}))
vi.mock('../../../stores/confirmStore', () => ({ confirmAsync }))
vi.mock('../../../hooks/useFocusTrap', () => ({ useFocusTrap: () => ({ current: null }) }))

import { useUIStore } from '../../../stores/uiStore'
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
  // The page renders this modal when the slot holds 'manage-views' and passes
  // closeModal as onClose — reproduce that wiring, not a vi.fn() stand-in.
  useUIStore.getState().openModal('manage-views')
  return render(
    <ManageViewsModal budgetId="b1" onClose={() => useUIStore.getState().closeModal()} />
  )
}

describe('ManageViewsModal', () => {
  beforeEach(() => {
    viewsState.data = []
    useUIStore.setState({ activeModal: null, activeViewId: null })
    vi.clearAllMocks()
    confirmAsync.mockResolvedValue(true)
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
    useUIStore.setState({ activeViewId: 'v2' })
    renderModal()
    expect(screen.getByText(/in use/)).toBeInTheDocument()
  })

  it('New View leaves the slot holding the editor, not null', () => {
    renderModal()
    fireEvent.click(screen.getByRole('button', { name: /New View/ }))
    expect(useUIStore.getState().activeModal).toEqual({ kind: 'view', editingId: null })
  })

  it('edit leaves the slot holding the editor for that view', () => {
    viewsState.data = [view('v1', 'Need / Want / Save')]
    renderModal()
    fireEvent.click(screen.getByLabelText('Edit view Need / Want / Save'))
    expect(useUIStore.getState().activeModal).toEqual({ kind: 'view', editingId: 'v1' })
  })

  it('delete asks first and does nothing when declined', async () => {
    viewsState.data = [view('v1', 'Need / Want / Save')]
    confirmAsync.mockResolvedValue(false)
    renderModal()
    fireEvent.click(screen.getByLabelText('Delete view Need / Want / Save'))
    await vi.waitFor(() => expect(confirmAsync).toHaveBeenCalled())
    expect(deleteMutate).not.toHaveBeenCalled()
  })

  it('deleting the active view falls back to the default groups', async () => {
    viewsState.data = [view('v1', 'Need / Want / Save')]
    useUIStore.setState({ activeViewId: 'v1' })
    renderModal()
    fireEvent.click(screen.getByLabelText('Delete view Need / Want / Save'))
    await vi.waitFor(() => expect(deleteMutate).toHaveBeenCalledWith('v1'))
    expect(useUIStore.getState().activeViewId).toBeNull()
  })

  it('deleting a view you are not looking at leaves the selection alone', async () => {
    viewsState.data = [view('v1', 'A'), view('v2', 'B')]
    useUIStore.setState({ activeViewId: 'v1' })
    renderModal()
    fireEvent.click(screen.getByLabelText('Delete view B'))
    await vi.waitFor(() => expect(deleteMutate).toHaveBeenCalledWith('v2'))
    expect(useUIStore.getState().activeViewId).toBe('v1')
  })
})
