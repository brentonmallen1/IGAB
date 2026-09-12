import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Header } from './Header'
import { useAppStore } from '../../../stores/appStore'
import { useUIStore } from '../../../stores/uiStore'

const isMobile = vi.hoisted(() => ({ value: false }))
vi.mock('../../../hooks/useMediaQuery', () => ({
  useIsMobile: () => isMobile.value,
  useIsTouch: () => isMobile.value,
}))
const aiEnabled = vi.hoisted(() => ({ value: true }))
vi.mock('../../../api/ai', () => ({
  useAIStatus: () => ({ data: { enabled: aiEnabled.value } }),
}))

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Header />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('Header on a phone', () => {
  beforeEach(() => {
    isMobile.value = true
    useAppStore.setState({ currentBudgetId: 'b1' })
  })

  it('keeps the month nav, search and the assistant on the budget route, nothing else', () => {
    // Nine 44px controls in 342px: every one shrank, the search button was
    // squeezed out entirely and the theme picker clipped at the edge.
    renderAt('/budget')
    expect(screen.getByRole('button', { name: 'Previous month' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Next month' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open command palette' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Undo last change' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Redo' })).toBeNull()
    expect(screen.queryByRole('button', { name: /privacy mode|Show amounts/ })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Change theme' })).toBeNull()
  })

  it('shows only search and the assistant elsewhere', () => {
    renderAt('/accounts')
    expect(screen.queryByRole('button', { name: 'Previous month' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Open command palette' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ask about your budget' })).toBeInTheDocument()
  })
})

describe('Header on desktop', () => {
  beforeEach(() => {
    isMobile.value = false
    useAppStore.setState({ currentBudgetId: 'b1' })
  })

  it('carries undo, redo, privacy and the theme controls', () => {
    renderAt('/budget')
    expect(screen.getByRole('button', { name: 'Undo last change' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Redo' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /privacy mode|Show amounts/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Change theme' })).toBeInTheDocument()
  })
})

describe.each([
  ['a phone', true],
  ['desktop', false],
])('the assistant button on %s', (_layout, mobile) => {
  beforeEach(() => {
    isMobile.value = mobile
    aiEnabled.value = true
    useAppStore.setState({ currentBudgetId: 'b1' })
    useUIStore.setState({ chatPanelOpen: false })
  })

  it('is there when AI is enabled and opens the assistant', () => {
    // On a phone it lived only in the More sheet, and the handoff from there
    // closed the assistant as it opened — the chat could not be reached.
    renderAt('/budget')
    fireEvent.click(screen.getByRole('button', { name: 'Ask about your budget' }))
    expect(useUIStore.getState().chatPanelOpen).toBe(true)
  })

  it('is absent when AI is disabled', () => {
    aiEnabled.value = false
    renderAt('/budget')
    expect(screen.queryByRole('button', { name: 'Ask about your budget' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Close the assistant' })).toBeNull()
  })
})
