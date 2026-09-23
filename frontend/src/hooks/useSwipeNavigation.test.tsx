import { describe, expect, it, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { useSwipeNavigation, type SwipeOptions } from './useSwipeNavigation'
import { popOverlay, pushOverlay } from '../utils/overlayStack'

vi.mock('../utils/haptics', () => ({ hapticTick: vi.fn() }))

function Surface(opts: SwipeOptions) {
  const handlers = useSwipeNavigation(opts)
  return <div data-testid="s" {...handlers} />
}

/** A page whose swipe surface contains a one-line horizontal scroller. */
function SurfaceWithScroller(opts: SwipeOptions & { fits?: boolean }) {
  const { fits, ...swipeOpts } = opts
  const handlers = useSwipeNavigation(swipeOpts)
  return (
    <div data-testid="s" {...handlers}>
      <div ref={measured(fits ? 390 : 476)} style={{ overflowX: 'auto' }}>
        <button data-testid="chip">Overspent</button>
      </div>
    </div>
  )
}

/** jsdom has no layout, so the strip's overflow has to be stated. */
function measured(scrollWidth: number) {
  return (el: HTMLElement | null) => {
    if (!el) return
    Object.defineProperty(el, 'scrollWidth', { value: scrollWidth, configurable: true })
    Object.defineProperty(el, 'clientWidth', { value: 390, configurable: true })
  }
}

function swipe(el: HTMLElement, from: [number, number], to: [number, number]) {
  fireEvent.touchStart(el, { touches: [{ clientX: from[0], clientY: from[1] }] })
  fireEvent.touchEnd(el, { changedTouches: [{ clientX: to[0], clientY: to[1] }] })
}

describe('useSwipeNavigation', () => {
  it('fires left and right for horizontal swipes away from the edge', () => {
    const onLeft = vi.fn()
    const onRight = vi.fn()
    const { getByTestId } = render(<Surface onLeft={onLeft} onRight={onRight} />)
    swipe(getByTestId('s'), [300, 100], [200, 104])
    swipe(getByTestId('s'), [200, 100], [300, 96])
    expect(onLeft).toHaveBeenCalledOnce()
    expect(onRight).toHaveBeenCalledOnce()
  })

  it('fires edge-back, not right, for a swipe that began at the left edge', () => {
    const onRight = vi.fn()
    const onEdgeBack = vi.fn()
    const { getByTestId } = render(<Surface onRight={onRight} onEdgeBack={onEdgeBack} />)
    swipe(getByTestId('s'), [8, 100], [120, 100])
    expect(onEdgeBack).toHaveBeenCalledOnce()
    expect(onRight).not.toHaveBeenCalled()
  })

  it('fires down for a downward drag, and a scroll-shaped diagonal never turns the page', () => {
    const onDown = vi.fn()
    const onLeft = vi.fn()
    const { getByTestId } = render(<Surface onDown={onDown} onLeft={onLeft} />)
    swipe(getByTestId('s'), [200, 100], [204, 200])
    swipe(getByTestId('s'), [200, 100], [130, 200])
    expect(onDown).toHaveBeenCalledTimes(2)
    expect(onLeft).not.toHaveBeenCalled()
  })

  it('does nothing on a scrolling page with no down handler', () => {
    const onLeft = vi.fn()
    const { getByTestId } = render(<Surface onLeft={onLeft} />)
    swipe(getByTestId('s'), [200, 100], [130, 200])
    expect(onLeft).not.toHaveBeenCalled()
  })

  it('does nothing while disabled — a pinch-zoomed image pans instead', () => {
    const onLeft = vi.fn()
    const { getByTestId } = render(<Surface onLeft={onLeft} enabled={false} />)
    swipe(getByTestId('s'), [300, 100], [100, 100])
    expect(onLeft).not.toHaveBeenCalled()
  })

  it('does nothing while an overlay covers the page', () => {
    // The mobile category inspector: a sheet that portals to document.body but
    // is still the budget page's child in the React tree, so its drags bubbled
    // to this handler and changed the month behind it.
    const onLeft = vi.fn()
    const { getByTestId } = render(<Surface pageLevel onLeft={onLeft} />)
    const sheet = Symbol('sheet')
    pushOverlay(sheet)
    try {
      swipe(getByTestId('s'), [300, 100], [100, 100])
      expect(onLeft).not.toHaveBeenCalled()
    } finally {
      popOverlay(sheet)
    }
    swipe(getByTestId('s'), [300, 100], [100, 100])
    expect(onLeft).toHaveBeenCalledOnce()
  })

  it('swallows the release of a gesture an overlay interrupted', () => {
    const onLeft = vi.fn()
    const { getByTestId } = render(<Surface pageLevel onLeft={onLeft} />)
    const el = getByTestId('s')
    fireEvent.touchStart(el, { touches: [{ clientX: 300, clientY: 100 }] })
    const sheet = Symbol('sheet')
    pushOverlay(sheet)
    try {
      fireEvent.touchEnd(el, { changedTouches: [{ clientX: 100, clientY: 100 }] })
      expect(onLeft).not.toHaveBeenCalled()
    } finally {
      popOverlay(sheet)
    }
  })

  it("still runs an overlay's own swipes while that overlay is open", () => {
    // The lightbox is the overlay; prev/next and swipe-down-to-close only ever
    // happen with one open, so it does not opt into pageLevel.
    const onLeft = vi.fn()
    const { getByTestId } = render(<Surface onLeft={onLeft} />)
    const lightbox = Symbol('lightbox')
    pushOverlay(lightbox)
    try {
      swipe(getByTestId('s'), [300, 100], [100, 100])
      expect(onLeft).toHaveBeenCalledOnce()
    } finally {
      popOverlay(lightbox)
    }
  })

  it('leaves a drag that began in a horizontal scroller to that scroller', () => {
    // Dragging the budget page's status-chip strip to reach its tail chips
    // used to change the month.
    const onLeft = vi.fn()
    const { getByTestId } = render(<SurfaceWithScroller onLeft={onLeft} />)
    swipe(getByTestId('chip'), [300, 100], [100, 100])
    expect(onLeft).not.toHaveBeenCalled()
  })

  it('turns the page from a strip whose chips all fit', () => {
    const onLeft = vi.fn()
    const { getByTestId } = render(<SurfaceWithScroller fits onLeft={onLeft} />)
    swipe(getByTestId('chip'), [300, 100], [100, 100])
    expect(onLeft).toHaveBeenCalledOnce()
  })
})
