/**
 * The tap/long-press disambiguation on transaction rows. The regression here:
 * the click-suppression flag was set by the long-press timer but cleared ONLY
 * by a subsequent click — iOS gestures that end without a click (text
 * selection takeover, touchcancel on scroll) left it latched, and the user's
 * next genuine tap was consumed just to clear it: "tap twice to edit".
 */
import { fireEvent, render, screen, act } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useLongPress } from './useLongPress'

function Probe({ onLong, onTap }: { onLong: () => void; onTap: () => void }) {
  const handlers = useLongPress(onLong, onTap)
  return <div data-testid="probe" {...handlers} />
}

function touch(
  el: Element,
  type: 'touchStart' | 'touchMove' | 'touchEnd' | 'touchCancel',
  x = 10,
  y = 10
) {
  fireEvent[type](el, { touches: [{ clientX: x, clientY: y }] })
}

describe('useLongPress', () => {
  const onLong = vi.fn()
  const onTap = vi.fn()

  beforeEach(() => {
    vi.useFakeTimers()
    onLong.mockClear()
    onTap.mockClear()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  function probe() {
    render(<Probe onLong={onLong} onTap={onTap} />)
    return screen.getByTestId('probe')
  }

  it('a short tap fires the tap handler once', () => {
    const el = probe()
    touch(el, 'touchStart')
    touch(el, 'touchEnd')
    fireEvent.click(el)
    expect(onTap).toHaveBeenCalledTimes(1)
    expect(onLong).not.toHaveBeenCalled()
  })

  it('a hold fires long-press and suppresses the synthetic click', () => {
    const el = probe()
    touch(el, 'touchStart')
    act(() => vi.advanceTimersByTime(600))
    touch(el, 'touchEnd')
    fireEvent.click(el)
    expect(onLong).toHaveBeenCalledTimes(1)
    expect(onTap).not.toHaveBeenCalled()
  })

  it('a tap AFTER a click-less long-press still works — the latch regression', () => {
    const el = probe()
    // Long-press whose synthetic click never arrives (iOS selection takeover)
    touch(el, 'touchStart')
    act(() => vi.advanceTimersByTime(600))
    touch(el, 'touchEnd')
    // No click event here — that's the point.

    // Next genuine tap must fire, not be eaten clearing the stale flag
    touch(el, 'touchStart')
    touch(el, 'touchEnd')
    fireEvent.click(el)
    expect(onTap).toHaveBeenCalledTimes(1)
  })

  it('touchcancel kills the pending timer — no long-press mid-scroll', () => {
    const el = probe()
    touch(el, 'touchStart')
    touch(el, 'touchCancel')
    act(() => vi.advanceTimersByTime(600))
    expect(onLong).not.toHaveBeenCalled()
    // And the next tap is clean
    touch(el, 'touchStart')
    touch(el, 'touchEnd')
    fireEvent.click(el)
    expect(onTap).toHaveBeenCalledTimes(1)
  })

  it('movement beyond the threshold cancels the press (scrolling)', () => {
    const el = probe()
    touch(el, 'touchStart', 10, 10)
    touch(el, 'touchMove', 10, 40)
    act(() => vi.advanceTimersByTime(600))
    expect(onLong).not.toHaveBeenCalled()
  })

  it('a tap after a completed long-press-with-click works', () => {
    const el = probe()
    touch(el, 'touchStart')
    act(() => vi.advanceTimersByTime(600))
    touch(el, 'touchEnd')
    fireEvent.click(el) // suppressed
    touch(el, 'touchStart')
    touch(el, 'touchEnd')
    fireEvent.click(el)
    expect(onLong).toHaveBeenCalledTimes(1)
    expect(onTap).toHaveBeenCalledTimes(1)
  })
})
