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

describe('placeAnchored — the panel decides the side, not a constant', () => {
  it('flips a tall panel that the room below cannot show (SystemTagsHelp)', () => {
    // The tags ⓘ popover is ~700px of content. With 300px below the trigger it
    // cleared the old 160px threshold, stayed below, and painted as a sliver
    // jammed against the bottom edge — capped correctly and unreadable.
    const p = placeAnchored(trigger({ top: 460, bottom: 484 }), VIEWPORT, {
      width: 440,
      desiredHeight: 700,
    })
    expect(p.top).toBeUndefined()
    expect(p.bottom).toBe(800 - 460 + 2)
    expect(p.maxHeight).toBe(460 - 8)
  })

  it('leaves a short menu below the same trigger (ContextMenu)', () => {
    // Same anchor, three items. Height is the only difference, and it is the
    // difference that decides — a menu is as tall as what it was given.
    const p = placeAnchored(trigger({ top: 460, bottom: 484 }), VIEWPORT, { desiredHeight: 90 })
    expect(p.top).toBe(486)
  })

  it('keeps below on a tie so a mid-page dropdown opens downward', () => {
    // spaceAbove must BEAT spaceBelow, not merely match it: a control in the
    // middle of the page flipping upward reads as a glitch.
    const p = placeAnchored(trigger({ top: 396, bottom: 404 }), VIEWPORT, { desiredHeight: 700 })
    expect(p.top).toBe(406)
  })

  it('falls back to the assumed height before the panel has been measured', () => {
    // First paint: nothing has rendered, so flipThreshold stands in. This is
    // the pre-existing behaviour and every unmeasured caller still gets it.
    const p = placeAnchored(trigger({ top: 700, bottom: 724 }), VIEWPORT, { flipThreshold: 160 })
    expect(p.bottom).toBe(800 - 700 + 2)
  })

  it('never asks for more room than the caller capped it at', () => {
    // A 700px panel under a 200px cap needs 200px, so 300px below is plenty.
    const p = placeAnchored(trigger({ top: 460, bottom: 484 }), VIEWPORT, {
      desiredHeight: 700,
      maxHeight: 200,
    })
    expect(p.top).toBe(486)
    expect(p.maxHeight).toBe(200)
  })
})

describe('placeAnchored — occluded viewport', () => {
  const KEYBOARD = { width: 1200, height: 800, inset: { top: 0, bottom: 300 } }

  it('does not open a panel under the keyboard', () => {
    // 800px of layout viewport, 300px of it covered. A trigger at 470 has
    // 22px of usable room below, not 322.
    const p = placeAnchored(trigger({ top: 446, bottom: 470 }), KEYBOARD, { desiredHeight: 200 })
    expect(p.top).toBeUndefined()
    expect(p.maxHeight).toBe(446 - 8)
  })

  it('measures the top inset too, so a scrolled visual viewport is honoured', () => {
    const shifted = { width: 1200, height: 800, inset: { top: 200, bottom: 0 } }
    const p = placeAnchored(trigger({ top: 260, bottom: 284 }), shifted, { desiredHeight: 900 })
    // Above holds 260-200-8 = 52; below holds 800-284-8 = 508. Below wins.
    expect(p.top).toBe(286)
    expect(p.maxHeight).toBe(508)
  })

  it('still measures `bottom` from the layout viewport when it flips', () => {
    // CSS `bottom` on a fixed element is relative to the layout viewport, so
    // the inset must not be subtracted here — that was the trap in expressing
    // occlusion by shrinking `height`.
    const p = placeAnchored(trigger({ top: 600, bottom: 624 }), KEYBOARD, { desiredHeight: 400 })
    expect(p.bottom).toBe(800 - 600 + 2)
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

describe('placeAnchored — align end', () => {
  it("puts the panel's right edge on the trigger's right edge", () => {
    // MoveMoneyPopover wrote this as `rect.right - 280` beside a CSS max-width
    // of 320: the inline copy won, the stylesheet's was free to say anything.
    const p = placeAnchored(trigger({ left: 600, width: 40 }), VIEWPORT, {
      width: 320,
      align: 'end',
    })
    expect(p.left).toBe(600 + 40 - 320)
  })

  it('still clamps inside the viewport on the left', () => {
    const p = placeAnchored(trigger({ left: 100, width: 40 }), VIEWPORT, {
      width: 320,
      align: 'end',
    })
    expect(p.left).toBe(8)
  })

  it('flips above near the bottom like everything else', () => {
    // The popover had no vertical clamp and no flip at all.
    const p = placeAnchored(trigger({ top: 740, bottom: 764, left: 600, width: 40 }), VIEWPORT, {
      width: 320,
      align: 'end',
    })
    expect(p.top).toBeUndefined()
    expect(p.bottom).toBe(800 - 740 + 2)
  })
})
