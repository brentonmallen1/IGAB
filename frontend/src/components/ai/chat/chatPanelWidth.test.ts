import { describe, expect, it } from 'vitest'
import { CHAT_PANEL_MAX_WIDTH, CHAT_PANEL_MIN_WIDTH, clampChatPanelWidth } from './chatPanelWidth'

describe('clampChatPanelWidth', () => {
  it('keeps a width inside the range', () => {
    expect(clampChatPanelWidth(420)).toBe(420)
  })

  it('clamps below the floor', () => {
    expect(clampChatPanelWidth(100)).toBe(CHAT_PANEL_MIN_WIDTH)
  })

  it('clamps above the ceiling', () => {
    // The panel sits beside the page, so an unbounded width squeezes the very
    // register it is meant to help you read.
    expect(clampChatPanelWidth(2000)).toBe(CHAT_PANEL_MAX_WIDTH)
  })

  it('rounds to whole pixels', () => {
    expect(clampChatPanelWidth(420.6)).toBe(421)
  })

  it('falls back to the floor for anything not a finite number', () => {
    // Matches clampSidebarWidth: a measurement that came back as NaN or
    // Infinity is a failed measurement, not a request for a huge panel.
    expect(clampChatPanelWidth(NaN)).toBe(CHAT_PANEL_MIN_WIDTH)
    expect(clampChatPanelWidth(Infinity)).toBe(CHAT_PANEL_MIN_WIDTH)
  })
})
