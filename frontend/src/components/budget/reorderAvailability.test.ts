import { describe, expect, it } from 'vitest'
import { canReorderCategories, canReorderGroups, reorderBlock } from './reorderAvailability'

const OPEN = {
  savedFilterActive: false,
  quickFilterActive: false,
  search: '',
  viewActive: false,
}

describe('reorderBlock', () => {
  it('is null when the grid shows the budget’s own arrangement', () => {
    expect(reorderBlock(OPEN)).toBeNull()
  })

  it.each([
    ['a saved filter', { savedFilterActive: true }],
    ['a quick filter', { quickFilterActive: true }],
    ['a search', { search: 'gro' }],
  ])('names the filter when %s is on', (_label, state) => {
    expect(reorderBlock({ ...OPEN, ...state })?.reason).toBe('filtered')
  })

  it('treats whitespace as no search', () => {
    // The grid trims before matching, so a space must not silently turn
    // dragging off while nothing appears to be filtered.
    expect(reorderBlock({ ...OPEN, search: '   ' })).toBeNull()
  })

  it('names the view, not the filter, when both are on', () => {
    // Clearing the filter would not give the handles back — the view still
    // owns the order — so naming the filter sends the user to do something
    // that changes nothing.
    const block = reorderBlock({ ...OPEN, viewActive: true, quickFilterActive: true })
    expect(block?.reason).toBe('view')
  })

  it('says both what is true and the way out', () => {
    for (const state of [
      { ...OPEN, viewActive: true },
      { ...OPEN, search: 'gro' },
    ]) {
      const block = reorderBlock(state)!
      expect(block.short.length).toBeGreaterThan(0)
      expect(block.detail).not.toEqual(block.short)
      // The detail is what the grid cannot say for itself: how to undo it.
      expect(block.detail.length).toBeGreaterThan(block.short.length)
    }
  })
})

describe('what the grid gates on', () => {
  it('offers both when nothing blocks and there are groups to order', () => {
    expect(canReorderCategories(OPEN)).toBe(true)
    expect(canReorderGroups(OPEN, 3)).toBe(true)
  })

  it('withholds both while filtered', () => {
    const filtered = { ...OPEN, quickFilterActive: true }
    expect(canReorderCategories(filtered)).toBe(false)
    expect(canReorderGroups(filtered, 3)).toBe(false)
  })

  it('withholds group ordering below two groups, without calling it a reason', () => {
    // A one-group budget has no ordering to lose, so the filter bar must stay
    // quiet — categories inside it are still perfectly reorderable.
    expect(canReorderGroups(OPEN, 1)).toBe(false)
    expect(canReorderGroups(OPEN, 0)).toBe(false)
    expect(reorderBlock(OPEN)).toBeNull()
    expect(canReorderCategories(OPEN)).toBe(true)
  })

  it('agrees with itself: the bar explains exactly when the grid withholds', () => {
    // The two used to be derived separately, and the failure mode was silent.
    for (const state of [
      OPEN,
      { ...OPEN, savedFilterActive: true },
      { ...OPEN, quickFilterActive: true },
      { ...OPEN, search: 'x' },
      { ...OPEN, viewActive: true },
      { ...OPEN, viewActive: true, search: 'x' },
    ]) {
      expect(canReorderCategories(state)).toBe(reorderBlock(state) === null)
    }
  })
})
