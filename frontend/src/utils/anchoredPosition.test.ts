/**
 * The cases here are the ones the five hand-rolled copies disagreed about.
 * Each `it` that mentions a component is naming a real defect that existed
 * before this was one function.
 */
import { describe, expect, it } from 'vitest'
import { placeAnchored, samePlacement, type AnchorRect } from './anchoredPosition'

const VIEWPORT = { width: 1200, height: 800 }
const trigger = (over: Partial<AnchorRect> = {}): AnchorRect => ({
  top: 100,
  bottom: 124,
  left: 300,
  width: 200,
  ...over,
})

describe('placeAnchored — vertical', () => {
  it('hangs below the trigger when there is room', () => {
    const p = placeAnchored(trigger(), VIEWPORT, { gap: 2 })
    expect(p.top).toBe(126)
    expect(p.bottom).toBeUndefined()
  })

  it('flips above when the room below is too small to be a placement', () => {
    // Combobox and MultiSelectCombobox never flipped: a control near the
    // bottom of the register opened its list off the screen.
    const p = placeAnchored(trigger({ top: 700, bottom: 724 }), VIEWPORT, { gap: 2 })
    expect(p.top).toBeUndefined()
    expect(p.bottom).toBe(800 - 700 + 2)
  })

  it('stays below when below is cramped but above is worse', () => {
    const p = placeAnchored(trigger({ top: 20, bottom: 44 }), { width: 1200, height: 200 }, {})
    expect(p.top).toBe(46)
  })

  it('caps height at the space available, under the preferred cap', () => {
    const p = placeAnchored(trigger({ top: 600, bottom: 624 }), VIEWPORT, { maxHeight: 300 })
    expect(p.maxHeight).toBe(800 - 624 - 8)
  })

  it('keeps the preferred cap when the space exceeds it', () => {
    const p = placeAnchored(trigger(), VIEWPORT, { maxHeight: 300 })
    expect(p.maxHeight).toBe(300)
  })
})

describe('placeAnchored — horizontal', () => {
  it('aligns to the trigger left edge', () => {
    expect(placeAnchored(trigger(), VIEWPORT, {}).left).toBe(300)
  })

  it('pulls a panel back inside the right edge', () => {
    // AssignDropdown and TagPicker clamped; Combobox, MultiSelectCombobox and
    // the first InfoPopover did not.
    const p = placeAnchored(trigger({ left: 1150 }), VIEWPORT, { width: 320, margin: 8 })
    expect(p.left).toBe(1200 - 320 - 8)
  })

  it('never places a panel off the left edge, even when it cannot fit', () => {
    const p = placeAnchored(trigger({ left: 4 }), { width: 300, height: 800 }, { width: 400 })
    expect(p.left).toBe(8)
    expect(p.width).toBe(300 - 16)
  })
})

describe('placeAnchored — width', () => {
  it("matches the trigger's width by default", () => {
    expect(placeAnchored(trigger({ width: 240 }), VIEWPORT, {}).width).toBe(240)
  })

  it('honours a fixed width over the trigger', () => {
    expect(placeAnchored(trigger(), VIEWPORT, { width: 420 }).width).toBe(420)
  })

  it('applies min and max around a trigger-derived width', () => {
    const narrow = placeAnchored(trigger({ width: 90 }), VIEWPORT, {
      width: 'trigger',
      minWidth: 200,
      maxWidth: 280,
    })
    const wide = placeAnchored(trigger({ width: 900 }), VIEWPORT, {
      width: 'trigger',
      minWidth: 200,
      maxWidth: 280,
    })
    expect(narrow.width).toBe(200)
    expect(wide.width).toBe(280)
  })
})

describe('samePlacement', () => {
  it('treats an unmoved trigger as no change', () => {
    const a = placeAnchored(trigger(), VIEWPORT, {})
    const b = placeAnchored(trigger(), VIEWPORT, {})
    expect(a).not.toBe(b)
    expect(samePlacement(a, b)).toBe(true)
  })

  it('sees a flip as a change', () => {
    const below = placeAnchored(trigger(), VIEWPORT, {})
    const above = placeAnchored(trigger({ top: 700, bottom: 724 }), VIEWPORT, {})
    expect(samePlacement(below, above)).toBe(false)
  })

  it('handles either side being unmeasured', () => {
    expect(samePlacement(null, null)).toBe(true)
    expect(samePlacement(placeAnchored(trigger(), VIEWPORT, {}), null)).toBe(false)
  })
})
