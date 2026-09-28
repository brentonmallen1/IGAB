import { describe, expect, it } from 'vitest'
import { chartColor } from './chartColors'
import {
  drawableTiles,
  flatTiles,
  groupColorKey,
  groupTiles,
  isTile,
  tileFontSize,
  tileLabel,
  treemapGroups,
  type TreemapGroup,
} from './treemapTiles'

describe('isTile', () => {
  it('skips the root recharts renders through the tile renderer', () => {
    // Depth 0, no name, no size: drawn, it printed "$0.00" mid-chart.
    expect(isTile({ depth: 0 })).toBe(false)
    expect(isTile({})).toBe(false)
  })

  it('draws a named node below the root', () => {
    expect(isTile({ depth: 1, name: 'Groceries' })).toBe(true)
  })

  it('skips an unnamed node at any depth, which has nothing to label', () => {
    expect(isTile({ depth: 1, name: '' })).toBe(false)
  })
})

const item = (id: string | null, parent_id: string | null, total: number) => ({
  id,
  name: id ?? 'Uncategorized',
  parent_id,
  parent_name: parent_id ? `Group ${parent_id}` : 'Uncategorized',
  total,
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
      ['fun', { key: 'fun', name: 'Fun', total: 200, colorIdx: 1, children: [] }],
      ['home', { key: 'home', name: 'Home', total: 1020, colorIdx: 0, children: [] }],
    ])
    const fills = Object.fromEntries(flatTiles(ITEMS, groups, 1220).map((t) => [t.id, t.fill]))
    expect(fills).toEqual({ rent: chartColor(0), power: chartColor(0), dining: chartColor(1) })
  })

  it('colours a group tile by its slot, not by its position in the list', () => {
    const groups = new Map<string, TreemapGroup>([
      ['fun', { key: 'fun', name: 'Fun', total: 200, colorIdx: 1, children: [] }],
      ['home', { key: 'home', name: 'Home', total: 1020, colorIdx: 0, children: [] }],
    ])
    const fills = Object.fromEntries(groupTiles(groups, 1220).map((t) => [t.name, t.fill]))
    expect(fills).toEqual({ Fun: chartColor(1), Home: chartColor(0) })
  })

  it('draws a group tile and its categories in one colour, in every mode', () => {
    const groups = treemapGroups(ITEMS)
    const groupFill = Object.fromEntries(groupTiles(groups, 1220).map((t) => [t.name, t.fill]))
    for (const tile of flatTiles(ITEMS, groups, 1220)) {
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

describe('share', () => {
  it('is of the group once drilled into, as the Breakdown states it', () => {
    // A drilled group's tiles stated their share of the whole period beside
    // a Breakdown that says "of what is on screen".
    const home = treemapGroups(ITEMS).get('home')!
    const rent = home.children.find((c) => c.name === 'rent')!
    expect(rent.pct).toBeCloseTo((900 / 1020) * 100, 5)
  })

  it('is of the whole period in category mode', () => {
    const groups = treemapGroups(ITEMS)
    const rent = flatTiles(ITEMS, groups, 1220).find((t) => t.name === 'rent')!
    expect(rent.pct).toBeCloseTo((900 / 1220) * 100, 5)
  })
})

describe('the Uncategorized line', () => {
  it('is a tile of its own that opens by "no category"', () => {
    const items = [...ITEMS, item(null, null, 40)]
    const tile = flatTiles(items, treemapGroups(items), 1260).find((t) => t.categoryId === null)!
    expect(tile).toMatchObject({ id: '__uncategorized__', name: 'Uncategorized' })
  })
})

describe('drawableTiles', () => {
  it('leaves off a line that netted to nothing or below, and counts it', () => {
    // Net of refunds: a category that took back more than it spent has no
    // area. It stays in the total; the page says how many were left off.
    const items = [...ITEMS, item('returns', 'fun', -90), item('quiet', 'fun', 0)]
    const { drawn, undrawn } = drawableTiles(flatTiles(items, treemapGroups(items), 1130))
    expect(drawn.map((t) => t.name)).toEqual(['rent', 'dining', 'power'])
    expect(undrawn).toBe(2)
  })
})

describe('groupColorKey', () => {
  it('names each group once, in the colour its tiles wear', () => {
    // Category mode shaded every tile by its group and named no group.
    const groups = treemapGroups(ITEMS)
    expect(groupColorKey(groups)).toEqual([
      { id: 'home', name: 'Group home', color: chartColor(0) },
      { id: 'fun', name: 'Group fun', color: chartColor(1) },
    ])
    for (const tile of flatTiles(ITEMS, groups, 1220)) {
      const key = groupColorKey(groups).find((k) => k.id === tile.groupKey)!
      expect(tile.fill).toBe(key.color)
    }
  })

  it('keeps two groups sharing a name as two keys', () => {
    // Keyed by name, they shared one legend entry and lit up together.
    const twins = [
      { id: 'a', name: 'Rent', parent_id: 'g1', parent_name: 'Bills', total: 100 },
      { id: 'b', name: 'Power', parent_id: 'g2', parent_name: 'Bills', total: 50 },
    ]
    const groups = treemapGroups(twins)
    expect(groupColorKey(groups).map((k) => k.id)).toEqual(['g1', 'g2'])
    expect(flatTiles(twins, groups, 150).map((t) => t.groupKey)).toEqual(['g1', 'g2'])
  })
})
