/**
 * The measuring half of the overlay rule. The arithmetic is pinned next door
 * in `utils/anchoredPosition.test.ts`; what is testable here is the one thing
 * the pure module cannot express — that reading a panel's natural height is an
 * *observation* and changes nothing about the panel.
 *
 * It was not. `measureNaturalHeight` lifts the panel's max-height to read
 * `scrollHeight`, and while the cap is off the panel's body no longer
 * overflows, so the browser clamps its `scrollTop` to 0. Putting the cap back
 * does not put the offset back. Because the placement is re-measured on every
 * scroll event, each wheel tick inside an open tags ⓘ popover measured the
 * panel and returned its body to the first line: the explanation opened, and
 * could not be read past its first screenful.
 *
 * jsdom has no layout, so `scrollTop` on a real element is always 0 and this
 * cannot be shown by rendering. A stub with the three properties the function
 * touches states the contract exactly, and states it about the function the
 * hook actually calls.
 */
import { describe, expect, it } from 'vitest'
import { measureNaturalHeight } from './useAnchoredPosition'

interface Scroller {
  scrollTop: number
}

/** A panel whose body scrolls, the shape InfoPopover/TagPicker/AssignDropdown
 *  all have: a flex column capped from the outside, with the scroll living on
 *  a child. `scrollHeight` reports the full content only while the cap is off,
 *  which is the whole reason the cap comes off. */
function panelWithScrollingBody(cap: string, contentHeight: number, bodyScrollTop: number) {
  const body: Scroller = { scrollTop: bodyScrollTop }
  const panel = {
    style: { maxHeight: cap },
    scrollTop: 0,
    querySelectorAll: () => [body] as unknown as NodeListOf<Element>,
    get scrollHeight() {
      return panel.style.maxHeight === 'none' ? contentHeight : Number.parseInt(cap, 10)
    },
  }
  return { panel: panel as unknown as HTMLElement, body }
}

describe('measureNaturalHeight', () => {
  it('reports the height the content wants, not the cap it is under', () => {
    const { panel } = panelWithScrollingBody('300px', 740, 0)
    expect(measureNaturalHeight(panel)).toBe(740)
  })

  it('puts the cap back', () => {
    const { panel } = panelWithScrollingBody('300px', 740, 0)
    measureNaturalHeight(panel)
    expect(panel.style.maxHeight).toBe('300px')
  })

  it('leaves a scrolled body where the reader left it', () => {
    // The defect: 420 became 0, on every scroll tick.
    const { panel, body } = panelWithScrollingBody('300px', 740, 420)
    measureNaturalHeight(panel)
    expect(body.scrollTop).toBe(420)
  })

  it('restores the panel itself when the panel is the scroller (ContextMenu)', () => {
    const panel = {
      style: { maxHeight: '280px' },
      scrollTop: 96,
      querySelectorAll: () => [] as unknown as NodeListOf<Element>,
      scrollHeight: 500,
    } as unknown as HTMLElement
    measureNaturalHeight(panel)
    expect(panel.scrollTop).toBe(96)
  })

  it('falls back rather than believing a panel that has not painted', () => {
    const panel = {
      style: { maxHeight: '' },
      scrollTop: 0,
      querySelectorAll: () => [] as unknown as NodeListOf<Element>,
      scrollHeight: 0,
    } as unknown as HTMLElement
    expect(measureNaturalHeight(panel)).toBeUndefined()
  })

  it('has nothing to measure without a panel', () => {
    expect(measureNaturalHeight(null)).toBeUndefined()
    expect(measureNaturalHeight(undefined)).toBeUndefined()
  })
})
