import { describe, expect, it } from 'vitest'
import { STICK_THRESHOLD_PX, isAtBottom } from './stickToBottom'

describe('isAtBottom', () => {
  it('is true when pinned to the bottom', () => {
    expect(isAtBottom({ scrollTop: 500, scrollHeight: 1000, clientHeight: 500 })).toBe(true)
  })

  it('is false when the user has scrolled up to read', () => {
    // The case the whole module exists for: following here would yank them
    // back to the bottom mid-sentence.
    expect(isAtBottom({ scrollTop: 100, scrollHeight: 1000, clientHeight: 500 })).toBe(false)
  })

  it('tolerates being a pixel or two short', () => {
    // Sub-pixel line heights and a mid-stream reflow leave a container just
    // shy of the bottom; a zero threshold would read that as scrolling away.
    expect(isAtBottom({ scrollTop: 495, scrollHeight: 1000, clientHeight: 500 })).toBe(true)
  })

  it('treats a container shorter than its viewport as at the bottom', () => {
    expect(isAtBottom({ scrollTop: 0, scrollHeight: 200, clientHeight: 500 })).toBe(true)
  })

  it('is exact at the threshold boundary', () => {
    const base = { scrollHeight: 1000, clientHeight: 500 }
    expect(isAtBottom({ ...base, scrollTop: 500 - STICK_THRESHOLD_PX })).toBe(true)
    expect(isAtBottom({ ...base, scrollTop: 500 - STICK_THRESHOLD_PX - 1 })).toBe(false)
  })

  it('accepts a custom threshold', () => {
    expect(isAtBottom({ scrollTop: 400, scrollHeight: 1000, clientHeight: 500 }, 0)).toBe(false)
    expect(isAtBottom({ scrollTop: 400, scrollHeight: 1000, clientHeight: 500 }, 200)).toBe(true)
  })
})
