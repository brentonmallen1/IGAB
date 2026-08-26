import { describe, expect, it } from 'vitest'
import { SIDEBAR_MAX_WIDTH, SIDEBAR_MIN_WIDTH, clampSidebarWidth } from './sidebarWidth'

describe('clampSidebarWidth', () => {
  it('keeps widths inside the range', () => {
    expect(clampSidebarWidth(300)).toBe(300)
    expect(clampSidebarWidth(SIDEBAR_MIN_WIDTH - 50)).toBe(SIDEBAR_MIN_WIDTH)
    expect(clampSidebarWidth(SIDEBAR_MAX_WIDTH + 50)).toBe(SIDEBAR_MAX_WIDTH)
  })
  it('rounds to whole pixels and rejects garbage', () => {
    expect(clampSidebarWidth(300.6)).toBe(301)
    expect(clampSidebarWidth(Number.NaN)).toBe(SIDEBAR_MIN_WIDTH)
    expect(clampSidebarWidth(Number.POSITIVE_INFINITY)).toBe(SIDEBAR_MIN_WIDTH)
  })
})
