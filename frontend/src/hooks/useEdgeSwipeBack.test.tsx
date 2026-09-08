import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { useEdgeSwipeBack } from './useEdgeSwipeBack'
import { popOverlay, pushOverlay } from '../utils/overlayStack'

vi.mock('../utils/haptics', () => ({ hapticTick: vi.fn() }))

function Shell() {
  const handlers = useEdgeSwipeBack()
  const { pathname } = useLocation()
  return (
    <div data-testid="content" {...handlers}>
      {pathname}
    </div>
  )
}

function at(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="*" element={<Shell />} />
      </Routes>
    </MemoryRouter>
  )
}

const edgeSwipe = (el: HTMLElement) => {
  fireEvent.touchStart(el, { touches: [{ clientX: 6, clientY: 300 }] })
  fireEvent.touchEnd(el, { changedTouches: [{ clientX: 140, clientY: 302 }] })
}

describe('useEdgeSwipeBack', () => {
  const id = Symbol('test-overlay')
  beforeEach(() => popOverlay(id))

  it('goes from a register back to the accounts list', () => {
    const { getByTestId } = at('/accounts/acc-1')
    edgeSwipe(getByTestId('content'))
    expect(getByTestId('content').textContent).toBe('/accounts')
  })

  it('does nothing while an overlay is open — the overlay owns its dismissal', () => {
    pushOverlay(id)
    const { getByTestId } = at('/accounts/acc-1')
    edgeSwipe(getByTestId('content'))
    expect(getByTestId('content').textContent).toBe('/accounts/acc-1')
  })

  it('ignores a swipe that did not start at the edge', () => {
    const { getByTestId } = at('/accounts/acc-1')
    fireEvent.touchStart(getByTestId('content'), { touches: [{ clientX: 200, clientY: 300 }] })
    fireEvent.touchEnd(getByTestId('content'), {
      changedTouches: [{ clientX: 340, clientY: 302 }],
    })
    expect(getByTestId('content').textContent).toBe('/accounts/acc-1')
  })

  it('stays put on the budget, which has no parent', () => {
    const { getByTestId } = at('/budget')
    edgeSwipe(getByTestId('content'))
    expect(getByTestId('content').textContent).toBe('/budget')
  })
})
