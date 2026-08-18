import { describe, expect, it, beforeEach } from 'vitest'
import { lockBodyScroll, scrollLockDepth, unlockBodyScroll } from './scrollLock'
import { isTopOverlay, overlayStackDepth, popOverlay, pushOverlay } from './overlayStack'

describe('scrollLock', () => {
  beforeEach(() => {
    while (scrollLockDepth() > 0) unlockBodyScroll()
    document.body.style.overflow = ''
  })

  it('locks and releases on a balanced pair', () => {
    lockBodyScroll()
    expect(document.body.style.overflow).toBe('hidden')
    unlockBodyScroll()
    expect(document.body.style.overflow).toBe('')
  })

  it('keeps the lock while an outer owner still holds it', () => {
    // The case that used to break: a lightbox opened from inside a sheet wrote
    // body.style.overflow directly, so closing it released the sheet's lock and
    // left the page scrollable behind a modal for the rest of the session.
    lockBodyScroll() // sheet
    lockBodyScroll() // lightbox
    unlockBodyScroll() // lightbox closes
    expect(document.body.style.overflow).toBe('hidden')
    unlockBodyScroll() // sheet closes
    expect(document.body.style.overflow).toBe('')
  })

  it('ignores an unmatched release rather than going negative', () => {
    unlockBodyScroll()
    expect(scrollLockDepth()).toBe(0)
    lockBodyScroll()
    expect(document.body.style.overflow).toBe('hidden')
    unlockBodyScroll()
    expect(document.body.style.overflow).toBe('')
  })
})

describe('overlayStack', () => {
  const a = Symbol('a')
  const b = Symbol('b')
  const c = Symbol('c')

  beforeEach(() => {
    for (const id of [a, b, c]) popOverlay(id)
  })

  it('routes a dismiss to the most recently opened overlay only', () => {
    pushOverlay(a)
    expect(isTopOverlay(a)).toBe(true)
    pushOverlay(b)
    expect(isTopOverlay(a)).toBe(false)
    expect(isTopOverlay(b)).toBe(true)
  })

  it('restores the previous overlay as top when the inner one closes', () => {
    pushOverlay(a)
    pushOverlay(b)
    popOverlay(b)
    expect(isTopOverlay(a)).toBe(true)
  })

  it('survives out-of-order removal', () => {
    pushOverlay(a)
    pushOverlay(b)
    pushOverlay(c)
    popOverlay(b) // middle closes first
    expect(isTopOverlay(c)).toBe(true)
    popOverlay(c)
    expect(isTopOverlay(a)).toBe(true)
    expect(overlayStackDepth()).toBe(1)
  })

  it('never reports a top overlay when nothing is open', () => {
    expect(isTopOverlay(a)).toBe(false)
    expect(overlayStackDepth()).toBe(0)
  })

  it('ignores a duplicate registration', () => {
    pushOverlay(a)
    pushOverlay(a)
    popOverlay(a)
    expect(overlayStackDepth()).toBe(0)
  })
})
