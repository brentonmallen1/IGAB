import { describe, expect, it, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { useSwipeNavigation, type SwipeOptions } from './useSwipeNavigation'

vi.mock('../utils/haptics', () => ({ hapticTick: vi.fn() }))

function Surface(opts: SwipeOptions) {
  const handlers = useSwipeNavigation(opts)
  return <div data-testid="s" {...handlers} />
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
})
