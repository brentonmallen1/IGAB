import { describe, expect, it } from 'vitest'
import { resolveSwipe, shouldDismissDrag } from './gestures'

describe('shouldDismissDrag', () => {
  it('dismisses on a slow drag past the distance threshold', () => {
    expect(shouldDismissDrag(100, 600)).toBe(true)
  })

  it('holds on a slow drag that stops short', () => {
    expect(shouldDismissDrag(60, 600)).toBe(false)
  })

  it('dismisses on a fast flick that never reached the distance threshold', () => {
    // 60px in 80ms = 0.75 px/ms. Distance alone made this do nothing, which is
    // what made the sheet feel stuck.
    expect(shouldDismissDrag(60, 80)).toBe(true)
  })

  it('ignores a fast twitch that barely moved', () => {
    expect(shouldDismissDrag(10, 5)).toBe(false)
  })

  it('ignores upward and zero drags', () => {
    expect(shouldDismissDrag(-50, 100)).toBe(false)
    expect(shouldDismissDrag(0, 100)).toBe(false)
  })

  it('does not divide by zero on a zero-duration gesture', () => {
    expect(shouldDismissDrag(30, 0)).toBe(false)
    expect(shouldDismissDrag(200, 0)).toBe(true)
  })
})

describe('resolveSwipe', () => {
  it('turns a page on a horizontal swipe past the threshold', () => {
    expect(resolveSwipe({ dx: -80, dy: 5, startX: 200 })).toBe('left')
    expect(resolveSwipe({ dx: 80, dy: -5, startX: 200 })).toBe('right')
  })

  it('is nothing for a short wobble or a tap', () => {
    expect(resolveSwipe({ dx: 30, dy: 2, startX: 200 })).toBeNull()
    expect(resolveSwipe({ dx: 0, dy: 0, startX: 200 })).toBeNull()
  })

  it('never turns a page on a diagonal scroll — axis dominance decides first', () => {
    // 70px across but 90px down: the finger was scrolling. That is a
    // downward gesture (a viewer may close on it), never a page swipe — and
    // a scrolling page simply has no down handler.
    expect(resolveSwipe({ dx: 70, dy: 90, startX: 200 })).toBe('down')
    expect(resolveSwipe({ dx: 70, dy: 90, startX: 200 })).not.toBe('right')
    // Short on both axes: nothing at all.
    expect(resolveSwipe({ dx: 30, dy: 40, startX: 200 })).toBeNull()
  })

  it('reads a downward drag past the threshold as down', () => {
    expect(resolveSwipe({ dx: 4, dy: 80, startX: 200 })).toBe('down')
    expect(resolveSwipe({ dx: 4, dy: -80, startX: 200 })).toBeNull()
  })

  it('reads a rightward swipe from the left edge as back, never as a page swipe', () => {
    // The installed PWA has no back gesture; this is the one the app supplies,
    // and the month swipe must not fire on the same touch.
    expect(resolveSwipe({ dx: 90, dy: 3, startX: 10 })).toBe('edge-back')
    expect(resolveSwipe({ dx: 90, dy: 3, startX: 24 })).toBe('edge-back')
    expect(resolveSwipe({ dx: 90, dy: 3, startX: 25 })).toBe('right')
  })

  it('ignores a leftward swipe that began in the edge zone', () => {
    expect(resolveSwipe({ dx: -90, dy: 3, startX: 10 })).toBeNull()
  })

  it('honours a caller-supplied threshold and edge', () => {
    expect(resolveSwipe({ dx: 40, dy: 0, startX: 200, threshold: 30 })).toBe('right')
    expect(resolveSwipe({ dx: 90, dy: 0, startX: 40, edgePx: 48 })).toBe('edge-back')
  })
})
