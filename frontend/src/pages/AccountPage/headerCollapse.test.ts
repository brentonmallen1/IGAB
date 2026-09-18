import { describe, expect, it } from 'vitest'

import { resolveHeaderCollapsed } from './headerCollapse'

describe('resolveHeaderCollapsed', () => {
  describe('when nobody has chosen', () => {
    it('folds on a phone', () => {
      // The full header left the register one row tall on a 390pt screen.
      expect(resolveHeaderCollapsed(null, true, false)).toBe(true)
    })

    it('stays open on a desktop', () => {
      expect(resolveHeaderCollapsed(null, false, false)).toBe(false)
    })
  })

  describe('once someone has chosen', () => {
    it('honours the choice over the viewport', () => {
      expect(resolveHeaderCollapsed(false, true, false)).toBe(false)
      expect(resolveHeaderCollapsed(true, false, false)).toBe(true)
    })
  })

  describe('while reconciling', () => {
    it('folds regardless of the stored choice', () => {
      // Someone who likes the header open still wants the rows while they
      // are ticking off a statement.
      expect(resolveHeaderCollapsed(false, false, true)).toBe(true)
      expect(resolveHeaderCollapsed(null, false, true)).toBe(true)
    })

    it('restores the choice when the reconcile ends', () => {
      // The property the derivation buys: nothing wrote over the stored
      // value, so there is nothing to put back. No ref, no effect, no
      // chance of a reconcile that is interrupted leaving the header folded
      // forever.
      const chosen = false
      expect(resolveHeaderCollapsed(chosen, false, true)).toBe(true)
      expect(resolveHeaderCollapsed(chosen, false, false)).toBe(chosen)
    })
  })
})
