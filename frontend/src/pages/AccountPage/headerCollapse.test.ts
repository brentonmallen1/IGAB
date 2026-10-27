import { describe, expect, it } from 'vitest'

import { resolveHeaderCollapsed } from './headerCollapse'

describe('resolveHeaderCollapsed', () => {
  it('stays open when nobody has chosen', () => {
    expect(resolveHeaderCollapsed(null, false)).toBe(false)
  })

  it('honours a choice once someone has made one', () => {
    expect(resolveHeaderCollapsed(false, false)).toBe(false)
    expect(resolveHeaderCollapsed(true, false)).toBe(true)
  })

  describe('while reconciling', () => {
    it('folds regardless of the stored choice', () => {
      // Someone who likes the header open still wants the rows while they
      // are ticking off a statement.
      expect(resolveHeaderCollapsed(false, true)).toBe(true)
      expect(resolveHeaderCollapsed(null, true)).toBe(true)
    })

    it('restores the choice when the reconcile ends', () => {
      // The property the derivation buys: nothing wrote over the stored
      // value, so there is nothing to put back. No ref, no effect, no
      // chance of a reconcile that is interrupted leaving the header folded
      // forever.
      const chosen = false
      expect(resolveHeaderCollapsed(chosen, true)).toBe(true)
      expect(resolveHeaderCollapsed(chosen, false)).toBe(chosen)
    })
  })
})
