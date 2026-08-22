/**
 * The boundary exists because of a real incident: a ReferenceError in the
 * budget filter bar unmounted the whole tree, and since the active view and
 * filter are persisted, reloading reproduced it immediately. There was no way
 * back in from the UI. Showing the error matters less than the escape hatch.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ErrorBoundary } from './ErrorBoundary'

function Boom(): never {
  throw new Error('filter is not defined')
}

const reload = vi.fn()

/** This environment ships without localStorage (the suite warns about it), so
 *  the boundary's escape hatch needs a real one to act on. */
function installStorage() {
  const store = new Map<string, string>()
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
      clear: () => store.clear(),
    },
  })
}

beforeEach(() => {
  // React logs caught render errors; that noise is expected here.
  vi.spyOn(console, 'error').mockImplementation(() => {})
  installStorage()
  localStorage.setItem('igab-ui', '{"activeViewId":"v1"}')
  localStorage.setItem('igab-reports', '{"activeTab":"pareto"}')
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { ...window.location, reload },
  })
})

afterEach(() => {
  vi.restoreAllMocks()
  reload.mockClear()
  localStorage.clear()
})

describe('ErrorBoundary', () => {
  it('renders children when nothing throws', () => {
    render(
      <ErrorBoundary>
        <p>the app</p>
      </ErrorBoundary>
    )
    expect(screen.getByText('the app')).toBeInTheDocument()
  })

  it('shows the error instead of a blank page', () => {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>
    )
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText(/filter is not defined/)).toBeInTheDocument()
  })

  it('reassures that nothing was saved or changed', () => {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>
    )
    expect(screen.getByText(/Your data is safe/)).toBeInTheDocument()
  })

  it('plain reload leaves saved selections alone', () => {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>
    )
    fireEvent.click(screen.getByText('Reload'))
    expect(localStorage.getItem('igab-ui')).not.toBeNull()
    expect(reload).toHaveBeenCalled()
  })

  it('the escape hatch clears the persisted state a crash can get stuck on', () => {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>
    )
    fireEvent.click(screen.getByText(/Reset saved view/))
    expect(localStorage.getItem('igab-ui')).toBeNull()
    expect(localStorage.getItem('igab-reports')).toBeNull()
    expect(reload).toHaveBeenCalled()
  })
})
