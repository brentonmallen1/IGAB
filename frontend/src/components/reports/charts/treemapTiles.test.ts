import { describe, expect, it } from 'vitest'
import { chartColor } from './chartColors'
import {
  flatTiles,
  groupTiles,
  tileFontSize,
  tileLabel,
  treemapGroups,
  type TreemapGroup,
} from './treemapTiles'

const item = (id: string, parent_id: string | null, total: number) => ({
  id,
  name: id,
  parent_id,
  parent_name: parent_id ? `Group ${parent_id}` : null,
  total,
  pct: 0,
})

const ITEMS = [item('rent', 'home', 900), item('dining', 'fun', 200), item('power', 'home', 120)]

describe('treemap colours', () => {
  it('gives a category its own group’s colour, not the next group’s', () => {
    // `colorIdx++` post-increments: children read the counter after it moved,
    // so none of a group's tiles matched the group tile just clicked.
    const groups = treemapGroups(ITEMS)
    expect(groups.get('home')!.children.map((c) => c.fill)).toEqual([chartColor(0), chartColor(0)])
    expect(groups.get('fun')!.children.map((c) => c.fill)).toEqual([chartColor(1)])
  })

  it('colours a flat tile by the group’s slot, not by where the group sits in the map', () => {
    // A map whose insertion order does not match the slots: `indexOf(gid)`
    // over the keys and the slot disagree here, and only the slot is right.
    const groups = new Map<string, TreemapGroup>([
      ['fun', { name: 'Fun', total: 200, colorIdx: 1, children: [] }],
      ['home', { name: 'Home', total: 1020, colorIdx: 0, children: [] }],
    ])
    const fills = Object.fromEntries(flatTiles(ITEMS, groups).map((t) => [t.id, t.fill]))
    expect(fills).toEqual({ rent: chartColor(0), power: chartColor(0), dining: chartColor(1) })
  })

  it('colours a group tile by its slot, not by its position in the list', () => {
    const groups = new Map<string, TreemapGroup>([
      ['fun', { name: 'Fun', total: 200, colorIdx: 1, children: [] }],
      ['home', { name: 'Home', total: 1020, colorIdx: 0, children: [] }],
    ])
    const fills = Object.fromEntries(groupTiles(groups, 1220).map((t) => [t.name, t.fill]))
    expect(fills).toEqual({ Fun: chartColor(1), Home: chartColor(0) })
  })

  it('draws a group tile and its categories in one colour, in every mode', () => {
    const groups = treemapGroups(ITEMS)
    const groupFill = Object.fromEntries(groupTiles(groups, 1220).map((t) => [t.name, t.fill]))
    for (const tile of flatTiles(ITEMS, groups)) {
      expect(tile.fill).toBe(groupFill[tile.parent_name as string])
    }
    for (const g of groups.values()) {
      for (const child of g.children) expect(child.fill).toBe(groupFill[g.name])
    }
  })
})

describe('group tiles', () => {
  it('sum their categories and state a share of the whole', () => {
    const [home] = groupTiles(treemapGroups(ITEMS), 1220)
    expect(home).toMatchObject({ name: 'Group home', size: 1020 })
    expect(home.pct).toBeCloseTo(83.6, 1)
  })

  it('state no share of a window with nothing spent', () => {
    expect(groupTiles(treemapGroups([item('a', 'g', 0)]), 0)[0].pct).toBeNull()
  })
})

describe('tileLabel', () => {
  it('cuts by the rule every chart shares, not one character wider', () => {
    // A 112px tile fits 16 characters. The tile's own copy kept `16 - 1` and
    // read "Harborstone Uti…" where Volatility, at 16, read "Harborstone Ut…".
    expect(tileLabel('Harborstone Utilities', 112)).toBe('Harborstone Ut…')
  })

  it('leaves a name that fits alone', () => {
    expect(tileLabel('Groceries', 112)).toBe('Groceries')
  })
})

describe('tileFontSize', () => {
  it('is 12px until the tile is too narrow for it', () => {
    expect(tileFontSize(200)).toBe(12)
    expect(tileFontSize(70)).toBe(10)
  })
})
