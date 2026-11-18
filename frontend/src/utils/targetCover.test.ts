import { describe, expect, it } from 'vitest'
import {
  coverRows,
  initialCoverIds,
  normalizeTargetCoverMode,
  sharedPick,
  shouldAskTargetCover,
  withPick,
} from './targetCover'

const bal = (category_id: string, target: number | null, cover: number | null) => ({
  category_id,
  target_assigned: target,
  cover_target_assigned: cover,
})

describe('coverRows', () => {
  it('lists the selected envelopes the server offers the choice on, with both figures', () => {
    const rows = coverRows(
      ['groceries', 'rent', 'fun'],
      [
        bal('groceries', 100, 130),
        bal('rent', 100, null),
        bal('fun', null, null),
        bal('dining', 100, 130), // not selected
      ],
      (id) => id.toUpperCase()
    )
    expect(rows).toEqual([{ categoryId: 'groceries', name: 'GROCERIES', target: 100, cover: 130 }])
  })
})

describe('the setting', () => {
  it('starts every row on Target unless it says Cover + target', () => {
    expect(initialCoverIds('ask', ['a', 'b'])).toEqual([])
    expect(initialCoverIds('target', ['a', 'b'])).toEqual([])
    expect(initialCoverIds('cover', ['a', 'b'])).toEqual(['a', 'b'])
  })

  it('asks only under Ask, and only when something is offered', () => {
    expect(shouldAskTargetCover('ask', 2)).toBe(true)
    expect(shouldAskTargetCover('ask', 0)).toBe(false)
    expect(shouldAskTargetCover('target', 2)).toBe(false)
    expect(shouldAskTargetCover('cover', 2)).toBe(false)
  })

  it('reads an unknown stored value as Ask', () => {
    expect(normalizeTargetCoverMode('cover')).toBe('cover')
    expect(normalizeTargetCoverMode('always')).toBe('ask')
    expect(normalizeTargetCoverMode(undefined)).toBe('ask')
  })
})

describe('picking', () => {
  it('"same for all" reads the shared pick, or neither when rows differ', () => {
    expect(sharedPick(['a', 'b'], new Set())).toBe('target')
    expect(sharedPick(['a', 'b'], new Set(['a', 'b']))).toBe('cover')
    expect(sharedPick(['a', 'b'], new Set(['a']))).toBeNull()
    expect(sharedPick([], new Set())).toBeNull()
  })

  it('applies one row’s pick without touching the others', () => {
    const start = new Set(['a'])
    expect(withPick(start, 'b', 'cover')).toEqual(new Set(['a', 'b']))
    expect(withPick(start, 'a', 'target')).toEqual(new Set())
    expect(start).toEqual(new Set(['a']))
  })
})
