import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MoreSheet } from './MoreSheet'
import { useUIStore } from '../../../stores/uiStore'

const undo = vi.hoisted(() => vi.fn(async () => {}))
const redo = vi.hoisted(() => vi.fn(async () => {}))
vi.mock('../../../hooks/useUndoRedo', () => ({
  useUndoRedo: () => ({ undo, redo, enabled: true }),
}))
vi.mock('../../../api/auth', () => ({
  useCurrentUser: () => ({ data: undefined }),
  useLogout: () => vi.fn(),
}))
vi.mock('../../../api/system', () => ({ useUpdateStatus: () => ({ data: undefined }) }))
vi.mock('../../../api/guide', () => ({ useGuideOverview: () => ({ data: undefined }) }))
vi.mock('../../ai/AIActivityNavBadge', () => ({ AIActivityNavBadge: () => null }))

function renderSheet() {
  const qc = new QueryClient()
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <MoreSheet />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('MoreSheet', () => {
  beforeEach(() => {
    window.matchMedia ??= (() => ({ matches: false })) as unknown as typeof window.matchMedia
    // A dialog opened by a previous test leaves its history entry behind and
    // closes this one on mount — drain it.
    window.history.replaceState(null, '', '/')
    useUIStore.setState({ moreSheetOpen: true })
    undo.mockClear()
    redo.mockClear()
  })

  it('has a title and a visible close button', () => {
    // An installed PWA has no back gesture; the drag handle and backdrop were
    // the only exits, and neither is visible.
    renderSheet()
    expect(screen.getByRole('dialog', { name: 'More' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument()
  })

  it('undoes and redoes, closing the sheet first so the toast is seen', () => {
    renderSheet()
    fireEvent.click(screen.getByRole('button', { name: 'Undo last change' }))
    expect(undo).toHaveBeenCalledOnce()
    expect(useUIStore.getState().moreSheetOpen).toBe(false)

    useUIStore.setState({ moreSheetOpen: true })
    fireEvent.click(screen.getByRole('button', { name: 'Redo' }))
    expect(redo).toHaveBeenCalledOnce()
    expect(useUIStore.getState().moreSheetOpen).toBe(false)
  })
})
