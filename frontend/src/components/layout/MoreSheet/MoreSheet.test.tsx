import { describe, expect, it, vi, beforeEach } from 'vitest'
import { act, render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MoreSheet } from './MoreSheet'
import { ChatPanel } from '../../ai/chat/ChatPanel'
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
vi.mock('../../../api/ai', () => ({ useAIStatus: () => ({ data: { enabled: true } }) }))
vi.mock('../../../api/aiChat', () => ({ useConversations: () => ({ data: [] }) }))
vi.mock('../../ai/chat/ChatThread', () => ({ ChatThread: () => null }))
vi.mock('../../../hooks/useMediaQuery', () => ({ useIsMobile: () => true, useIsTouch: () => true }))

/** A UI close defers history.back() a tick, and popstate is queued after it. */
const settle = () => act(() => new Promise((resolve) => setTimeout(resolve, 30)))

function renderSheet() {
  const qc = new QueryClient()
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <MoreSheet />
        <ChatPanel />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('MoreSheet', () => {
  beforeEach(async () => {
    window.matchMedia ??= (() => ({ matches: false })) as unknown as typeof window.matchMedia
    // A dialog opened by a previous test leaves its history entry behind, and
    // a sheet it closed leaves a deferred back() still to land — either closes
    // this test's sheets. Let the back() run, then drain the entry.
    await settle()
    window.history.replaceState(null, '', '/')
    useUIStore.setState({ moreSheetOpen: true, chatPanelOpen: false })
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

  it('"Ask about your budget" hands off to the assistant, which stays open', async () => {
    // Closing More scheduled history.back() for its entry; the assistant's
    // sheet pushed its own in the same click, and the deferred back() popped
    // that instead — the assistant flashed open and closed again.
    renderSheet()
    fireEvent.click(screen.getByRole('button', { name: 'Ask about your budget' }))
    await settle()

    expect(useUIStore.getState().moreSheetOpen).toBe(false)
    expect(useUIStore.getState().chatPanelOpen).toBe(true)
    expect(screen.getByRole('dialog', { name: 'Ask about your budget' })).toBeInTheDocument()
    expect((window.history.state as { igabSheet?: string } | null)?.igabSheet).toBe('ai-chat')
  })
})
