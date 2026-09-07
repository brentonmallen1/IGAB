/**
 * The budget bar's chips must not grow with the number of saved filters.
 *
 * The bar wraps, and the grid offsets its sticky column header by this bar's
 * measured height — so one button per saved filter meant every filter someone
 * saved pushed the register further down the page. That gets worse the more
 * they use the feature, which is the wrong direction for anything to get worse
 * in.
 *
 * The pixel half of this is measured in headless Chrome
 * (`budgetFilterBarHeight.test.ts`); this is the rule that decides it.
 */
import { describe, expect, it } from 'vitest'
import { PINNED_FILTER_COUNT, filterChips } from './budgetFilterChips'

const saved = (n: number) =>
  Array.from({ length: n }, (_, i) => ({ id: `f${i}`, name: `Filter ${i}` }))

describe('how many chips the bar draws', () => {
  it('draws them all while there are few', () => {
    const { chips, overflow } = filterChips(saved(3), null)
    expect(chips.map((f) => f.id)).toEqual(['f0', 'f1', 'f2'])
    expect(overflow).toEqual([])
  })

  it('stops at the pinned count however many are saved', () => {
    for (const count of [4, 12, 25]) {
      const { chips, overflow } = filterChips(saved(count), null)
      expect(chips).toHaveLength(PINNED_FILTER_COUNT)
      expect(overflow).toHaveLength(count - PINNED_FILTER_COUNT)
    }
  })

  it('pins by the order the user put them in', () => {
    // `sort_order` is already the user's statement — Manage Filters reorders
    // it — so "the ones I put first" needs no second column to say it.
    const { chips } = filterChips(saved(10), null)
    expect(chips.map((f) => f.id)).toEqual(['f0', 'f1', 'f2'])
  })
})

describe('the active filter', () => {
  it('gets a chip even when it is not pinned', () => {
    // The bar's job is to say what is narrowing the grid. Hiding that in the
    // picker leaves a short category list with no visible reason for it.
    const { chips, overflow } = filterChips(saved(10), 'f7')
    expect(chips.map((f) => f.id)).toEqual(['f0', 'f1', 'f2', 'f7'])
    expect(overflow.map((f) => f.id)).not.toContain('f7')
  })

  it('is appended rather than swapped in, so the pinned three stay put', () => {
    // Choosing from the picker must not reshuffle the chips someone navigates
    // by position.
    const { chips } = filterChips(saved(10), 'f9')
    expect(chips.slice(0, 3).map((f) => f.id)).toEqual(['f0', 'f1', 'f2'])
  })

  it('adds no fourth chip when the active one is already pinned', () => {
    const { chips } = filterChips(saved(10), 'f1')
    expect(chips).toHaveLength(PINNED_FILTER_COUNT)
  })

  it('bounds the chips at pinned + 1, whatever is active', () => {
    for (const active of ['f0', 'f5', 'f24', null]) {
      const { chips } = filterChips(saved(25), active)
      expect(chips.length).toBeLessThanOrEqual(PINNED_FILTER_COUNT + 1)
    }
  })

  it('ignores an id that is not in the list', () => {
    // A filter deleted in another tab, or one persisted from another budget.
    const { chips, overflow } = filterChips(saved(10), 'gone')
    expect(chips).toHaveLength(PINNED_FILTER_COUNT)
    expect(overflow).toHaveLength(7)
  })
})

describe('edge cases the bar actually hits', () => {
  it('draws nothing for a budget with no saved filters', () => {
    expect(filterChips([], null)).toEqual({ chips: [], overflow: [] })
  })

  it('offers no picker when everything already has a chip', () => {
    expect(filterChips(saved(PINNED_FILTER_COUNT), 'f0').overflow).toEqual([])
  })
})
