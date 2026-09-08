import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Header } from './Header'
import { useAppStore } from '../../../stores/appStore'

const isMobile = vi.hoisted(() => ({ value: false }))
vi.mock('../../../hooks/useMediaQuery', () => ({
  useIsMobile: () => isMobile.value,
  useIsTouch: () => isMobile.value,
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

  it('keeps the month nav and search on the budget route, nothing else', () => {
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

  it('shows only search elsewhere', () => {
    renderAt('/accounts')
    expect(screen.queryByRole('button', { name: 'Previous month' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Open command palette' })).toBeInTheDocument()
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
