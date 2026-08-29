/**
 * Mirrors backend/tests/unit/test_ordering.py case for case: the optimistic
 * order the grid shows must be the order the server then stores.
 */
import { describe, expect, it } from 'vitest'
import { moveItem, reorderMembers } from './listOrder'

describe('moveItem', () => {
  it('moves forward and backward', () => {
    expect(moveItem(['a', 'b', 'c'], 0, 2)).toEqual(['b', 'c', 'a'])
    expect(moveItem(['a', 'b', 'c'], 2, 0)).toEqual(['c', 'a', 'b'])
  })

  it('returns the same list for a no-op or an out-of-range move', () => {
    const list = ['a', 'b', 'c']
    expect(moveItem(list, 1, 1)).toBe(list)
    expect(moveItem(list, -1, 0)).toBe(list)
    expect(moveItem(list, 0, 3)).toBe(list)
  })
})

function row(id: string, group: string, sort_order: number) {
  return { id, group, sort_order }
}

describe('reorderMembers', () => {
  const inGroup = (g: string) => (item: { group: string }) => item.group === g

  it('a full list is taken as given, renumbered', () => {
    const list = [row('a', 'g', 0), row('b', 'g', 1), row('c', 'g', 2)]
    expect(reorderMembers(list, inGroup('g'), ['c', 'a', 'b'])).toEqual([
      row('c', 'g', 0),
      row('a', 'g', 1),
      row('b', 'g', 2),
    ])
  })

  it('an omitted (hidden) member keeps its slot', () => {
    const list = [row('a', 'g', 0), row('b', 'g', 1), row('c', 'g', 2)]
    expect(reorderMembers(list, inGroup('g'), ['c', 'a'])).toEqual([
      row('c', 'g', 0),
      row('b', 'g', 1),
      row('a', 'g', 2),
    ])
  })

  it('leaves other groups exactly where they were', () => {
    const list = [row('x', 'other', 0), row('a', 'g', 0), row('y', 'other', 1), row('b', 'g', 1)]
    expect(reorderMembers(list, inGroup('g'), ['b', 'a'])).toEqual([
      row('x', 'other', 0),
      row('b', 'g', 0),
      row('y', 'other', 1),
      row('a', 'g', 1),
    ])
  })

  it('ignores an id that is not a member', () => {
    const list = [row('a', 'g', 0), row('b', 'g', 1)]
    expect(reorderMembers(list, inGroup('g'), ['b', 'zzz', 'a'])).toEqual([
      row('b', 'g', 0),
      row('a', 'g', 1),
    ])
  })
})
