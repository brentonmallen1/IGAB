import { describe, expect, it } from 'vitest'
import {
  concentrationSentence,
  cumulativeShares,
  exportRows,
  groupCategoryLines,
  indexTo80,
  rankedLines,
  rankedTable,
  runningLabel,
  shareLabel,
  type RankedLines,
} from './whereItWent'
import pareto from '../../../../../shared/pareto_cases.json'

const item = (
  id: string | null,
  name: string,
  total: number,
  parent_id: string | null,
  parent_name: string
) => ({ id, name, total, parent_id, parent_name })

const spending = [
  item('c1', 'Groceries', 300, 'g1', 'Everyday'),
  item('c2', 'Gas', 100, 'g1', 'Everyday'),
  item('c3', 'Rent', 600, 'g2', 'Home'),
]
const payees = [
  { payee_id: 'p1', payee_name: 'Corner Market', total: '250' },
  { payee_id: 'p2', payee_name: 'Harborstone Rentals', total: '600' },
]

describe('rankedLines', () => {
  it('category mode ranks largest first against the served total', () => {
    const { lines, total, universeCount } = rankedLines('category', spending, '1000', undefined)
    expect(lines.map((l) => l.name)).toEqual(['Rent', 'Groceries', 'Gas'])
    expect(lines[1]).toMatchObject({ id: 'c1', groupName: 'Everyday', members: ['c1'] })
    expect(total).toBe(1000)
    expect(universeCount).toBe(3)
  })

  it('group mode sums each group and states shares of the served total too', () => {
    // Pareto's group mode summed its own total while the Breakdown and the
    // Treemap read the served one: the same figure until a cent of rounding.
    const { lines, total } = rankedLines('group', spending, '1000', undefined)
    expect(lines).toEqual([
      { id: 'g2', name: 'Home', total: 600, groupName: null, members: ['c3'] },
      { id: 'g1', name: 'Everyday', total: 400, groupName: null, members: ['c1', 'c2'] },
    ])
    expect(total).toBe(1000)
  })

  it('group mode sums a group exactly as the treemap tiles do', () => {
    // One aggregation (`treemapGroups`) behind the table and the tiles, so a
    // group cannot read one figure in the table and another as a tile.
    const odd = [...spending, item('c4', 'Tolls', 0.1, 'g1', 'Everyday')]
    const everyday = rankedLines('group', odd, '1000.1', undefined).lines.find(
      (l) => l.id === 'g1'
    )!
    expect(everyday.total).toBeCloseTo(400.1, 10)
  })

  it('the served Uncategorized line opens by "no category", as a line and as a group', () => {
    const line = [item(null, 'Uncategorized', 40, null, 'Uncategorized')]
    expect(rankedLines('category', line, '40', undefined).lines[0]).toMatchObject({
      id: '__uncategorized__',
      members: [null],
    })
    expect(rankedLines('group', line, '40', undefined).lines[0]).toMatchObject({
      name: 'Uncategorized',
      members: [null],
    })
  })

  it('a line that took back more than it spent sorts last, signed', () => {
    const refunded = [...spending, item('c4', 'Shopping', -90, 'g1', 'Everyday')]
    const { lines } = rankedLines('category', refunded, '910', undefined)
    expect(lines.at(-1)).toMatchObject({ name: 'Shopping', total: -90 })
  })

  it('payee mode reads the served total, count and 80% line, never the ranked rows', () => {
    // The server ranks the top 25 and totals every payee. Summing the ranked
    // rows made concentration a fact about the cap.
    const r = rankedLines('payee', spending, undefined, {
      payees,
      total: '4000',
      payee_count: 312,
      payees_to_80pct: 140,
    })
    expect(r.lines.map((l) => l.name)).toEqual(['Harborstone Rentals', 'Corner Market'])
    expect(r.lines[0]).toMatchObject({ id: 'p2', groupName: null, members: [] })
    expect([r.total, r.universeCount, r.servedTo80]).toEqual([4000, 312, 140])
  })

  it('payee mode with no response has no payees, not a total summed from nothing', () => {
    expect(rankedLines('payee', spending, undefined, undefined)).toEqual({
      lines: [],
      total: 0,
      universeCount: 0,
      servedTo80: null,
    })
  })
})

describe('groupCategoryLines', () => {
  it("ranks an opened group's categories against the group's own total", () => {
    const home = groupCategoryLines(spending, 'g1')!
    expect(home.name).toBe('Everyday')
    expect(home.lines.map((l) => l.name)).toEqual(['Groceries', 'Gas'])
    expect(home.total).toBe(400)
    expect(home.universeCount).toBe(2)
  })

  it('adds up to the line the group had in the group table', () => {
    // Opening a group and listing its transactions must total what the
    // group's row said.
    const groupLine = rankedLines('group', spending, '1000', undefined).lines.find(
      (l) => l.id === 'g1'
    )!
    const opened = groupCategoryLines(spending, 'g1')!
    expect(opened.total).toBe(groupLine.total)
    expect(opened.lines.flatMap((l) => l.members).sort()).toEqual([...groupLine.members].sort())
  })

  it('opens the Uncategorized group, which has no id', () => {
    const items = [...spending, item(null, 'Uncategorized', 40, null, 'Uncategorized')]
    const opened = groupCategoryLines(items, '__none__')!
    expect(opened.lines).toEqual([
      {
        id: '__uncategorized__',
        name: 'Uncategorized',
        total: 40,
        groupName: 'Uncategorized',
        members: [null],
      },
    ])
  })

  it('is null for a key the data no longer holds', () => {
    // A view switched under an open group replaces every group key.
    expect(groupCategoryLines(spending, 'gone')).toBeNull()
  })
})

const lines = (totals: number[]) =>
  totals.map((total, i) => ({ id: `i${i}`, name: `n${i}`, total, groupName: null, members: [] }))

describe('cumulativeShares', () => {
  it('runs up to 100 when the lines cover the total', () => {
    expect(cumulativeShares(lines([50, 30, 20]), 100)).toEqual([50, 80, 100])
  })

  it('runs past 100 and back when a line netted negative', () => {
    // Net of refunds, the positive lines are more than the total; the
    // refund-heavy line, listed last, brings it back.
    const shares = cumulativeShares(lines([60, 50, -10]), 100)
    expect(shares.map((s) => Math.round(s!))).toEqual([60, 110, 100])
  })

  it('reaches a line it meets exactly, which dollar floats fall a hair short of', () => {
    // 0.70 + 0.10 is 0.7999999999999999 in floating point: summed in dollars,
    // the running share read 79.99…% and the 80% line moved down a row.
    const shares = cumulativeShares(lines([0.7, 0.1, 0.2]), 1)
    expect(shares[1]).toBe(80)
    expect(indexTo80(shares)).toBe(1)
  })

  it('states no share with no positive total to be a share of', () => {
    // The old chart drew these on the axis at 0; a table can say "—".
    expect(cumulativeShares(lines([1, 2]), 0)).toEqual([null, null])
    expect(cumulativeShares(lines([10, -40]), -30)).toEqual([null, null])
  })
})

describe('indexTo80', () => {
  it('finds the line whose running share reaches 80%, inclusively', () => {
    expect(indexTo80([50, 80, 100])).toBe(1)
    expect(indexTo80([80, 100])).toBe(0)
  })

  it('finds nothing when no share reaches 80%, or none can be stated', () => {
    expect(indexTo80([10, 20])).toBe(-1)
    expect(indexTo80([null, null])).toBe(-1)
  })

  it('takes the served count in payee mode, where the client holds only 25', () => {
    // 312 payees, the top 25 holding $4,120 of $9,850: their running share
    // peaks at 41.8% and looking for 80% in it found nothing.
    const top25 = cumulativeShares(lines(Array(25).fill(4120 / 25)), 9850)
    expect(indexTo80(top25)).toBe(-1)
    expect(indexTo80(top25, 140)).toBe(139)
    expect(indexTo80([], null)).toBe(-1)
  })
})

describe('the 80% line, against the cases the backend runs', () => {
  // Category and group modes count it here; payee mode is served it by
  // `domain/concentration.py`. One fixture holds both to the same answer.
  it.each(pareto.cases)('$note', ({ totals, items_to_80 }) => {
    const sum = totals.reduce((s, t) => s + t, 0)
    const idx = indexTo80(cumulativeShares(lines(totals), sum))
    expect(idx === -1 ? null : idx + 1).toBe(items_to_80)
  })
})

const ranked = (totals: number[], total: number, extra: Partial<RankedLines> = {}) =>
  rankedTable({ lines: lines(totals), total, universeCount: totals.length, ...extra })

describe('rankedTable', () => {
  it('states each share, the running share, and marks the line that reaches 80%', () => {
    const t = ranked([50, 30, 20], 100)
    expect(t.rows.map((r) => [r.share, r.cumulative, r.crosses80])).toEqual([
      [50, 50, false],
      [30, 80, true],
      [20, 100, false],
    ])
    expect(t.to80).toBe(2)
  })

  it('counts past twenty lines, where the old chart stopped measuring', () => {
    // Forty equal categories: 80% is reached at the 32nd. The chart measured
    // its twenty drawn bars, whose line tops out at 50%, and the card vanished.
    const t = ranked(Array(40).fill(25), 1000)
    expect(t.to80).toBe(32)
    expect(t.rows[31].crosses80).toBe(true)
  })

  it('marks no row in payee mode when the 80% line is past the 25 listed', () => {
    const t = ranked(Array(25).fill(4120 / 25), 9850, { universeCount: 312, servedTo80: 140 })
    expect(t.to80).toBe(140)
    expect(t.rows.some((r) => r.crosses80)).toBe(false)
  })

  it('states a negative share for a line that took back more than it spent', () => {
    const t = ranked([600, 500, -100], 1000)
    expect(t.rows[2]).toMatchObject({ share: -10, cumulative: 100, crosses80: false })
    expect(t.rows[1].crosses80).toBe(true)
  })

  it('has no shares and no 80% line when refunds beat spending', () => {
    const t = ranked([40, -100], -60)
    expect(t.rows.map((r) => [r.share, r.cumulative])).toEqual([
      [null, null],
      [null, null],
    ])
    expect(t.to80).toBeNull()
  })

  it('has no 80% line when nothing was spent', () => {
    expect(ranked([0, 0], 0).to80).toBeNull()
    expect(ranked([], 0)).toEqual({ rows: [], to80: null })
  })
})

describe('concentrationSentence', () => {
  it('says how few lines make 80% of spending', () => {
    expect(concentrationSentence(12, 56, 'category')).toBe(
      '12 of 56 categories make 80% of spending'
    )
    expect(concentrationSentence(140, 312, 'payee')).toBe('140 of 312 payees make 80% of spending')
    expect(concentrationSentence(3, 9, 'group')).toBe('3 of 9 groups make 80% of spending')
  })

  it('agrees in number', () => {
    expect(concentrationSentence(1, 56, 'category')).toBe(
      '1 of 56 categories makes 80% of spending'
    )
    expect(concentrationSentence(1, 1, 'payee')).toBe('1 of 1 payee makes 80% of spending')
  })

  it('names an opened group', () => {
    expect(concentrationSentence(2, 7, 'category', 'Home')).toBe(
      '2 of 7 categories make 80% of the spending in Home'
    )
  })

  it('says nothing where there is no 80% line', () => {
    expect(concentrationSentence(null, 12, 'category')).toBeNull()
    expect(concentrationSentence(1, 0, 'category')).toBeNull()
  })

  it('gives no verdict on the shape', () => {
    // Pareto added "concentrated — easier to optimize" or "spread thin —
    // consider consolidating" at a 30% threshold, in warning colour.
    for (const [n, of] of [
      [1, 50],
      [40, 50],
    ]) {
      expect(concentrationSentence(n, of, 'category')).not.toMatch(/concentrat|spread|consider/)
    }
  })
})

describe('shareLabel and runningLabel', () => {
  it('print tenths, cut rather than rounded', () => {
    expect(shareLabel(29.66)).toBe('29.6%')
    expect(runningLabel(29.66)).toBe('29.6%')
  })

  it('print a row above the 80% mark below 80, and 100 only once every line is in', () => {
    // Rounded, 79.96% read "80.0%" above the line that says 80% is reached.
    expect(runningLabel(79.96)).toBe('79.9%')
    expect(runningLabel(80)).toBe('80.0%')
    expect(runningLabel(99.96)).toBe('99.9%')
    expect(runningLabel(100)).toBe('100.0%')
  })

  it("print the first row's share and running share alike", () => {
    // Rounding one and cutting the other read "24%" beside "23%".
    expect(shareLabel(23.69)).toBe(runningLabel(23.69))
  })

  it('keep a figure floating point lands a hair under', () => {
    expect(0.57 * 100).toBeLessThan(57)
    expect(runningLabel(0.57 * 100)).toBe('57.0%')
  })

  it('say "<0.1%" for a line too small to print, not "0.0%"', () => {
    expect(shareLabel(0.04)).toBe('<0.1%')
    expect(shareLabel(0)).toBe('0.0%')
  })

  it('sign a line that took back more than it spent, cut toward zero', () => {
    expect(shareLabel(-11.11)).toBe('-11.1%')
  })

  it('dash a missing share', () => {
    expect(shareLabel(null)).toBe('—')
    expect(runningLabel(null)).toBe('—')
  })
})

describe('exportRows', () => {
  it('exports the table as it reads: name, group, spent, share and running share', () => {
    const table = rankedTable(rankedLines('category', spending, '1000', undefined))
    expect(exportRows(table)).toEqual([
      { name: 'Rent', group: 'Home', spent: 600, share_pct: 60, cumulative_pct: 60 },
      { name: 'Groceries', group: 'Everyday', spent: 300, share_pct: 30, cumulative_pct: 90 },
      { name: 'Gas', group: 'Everyday', spent: 100, share_pct: 10, cumulative_pct: 100 },
    ])
  })
})
