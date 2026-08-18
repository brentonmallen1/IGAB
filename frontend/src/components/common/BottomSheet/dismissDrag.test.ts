import { describe, expect, it } from 'vitest'
import { shouldDismissDrag } from './dismissDrag'

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
