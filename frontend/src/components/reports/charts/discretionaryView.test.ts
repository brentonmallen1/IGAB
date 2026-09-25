import { describe, expect, it } from 'vitest'
import type { DiscretionaryGroup } from '../../../types'
import {
  discretionaryDrill,
  discretionaryMonthDrill,
  discretionaryRows,
  discretionaryShare,
} from './discretionaryView'

// The household the backend suite builds (test_discretionary.py), over one
// month: Everyday 500 (Dining Out 450, Coffee 50), Fun 150, and 75 of
// uncategorized spending — 725 in all, of 2,215 spent.
const GROUPS: DiscretionaryGroup[] = [
  {
    group_id: 'g-everyday',
    group_name: 'Everyday',
    total: 500,
    avg_monthly: 500,
    categories: [
      { category_id: 'c-dining', category_name: 'Dining Out', total: 450, avg_monthly: 450 },
      { category_id: 'c-coffee', category_name: 'Coffee', total: 50, avg_monthly: 50 },
    ],
  },
  {
    group_id: 'g-fun',
    group_name: 'Fun',
    total: 150,
    avg_monthly: 150,
    categories: [
      { category_id: 'c-hobbies', category_name: 'Hobbies', total: 150, avg_monthly: 150 },
    ],
  },
  { group_id: null, group_name: 'Uncategorized', total: 75, avg_monthly: 75, categories: [] },
]

const WINDOW = { startDate: '2026-08-01', endDate: '2026-08-31' }

describe('discretionaryShare', () => {
  it('is discretionary as a share of all spending', () => {
    // 725 of 2,215.
    expect(discretionaryShare({ total: 725, spending_total: 2215 })).toBeCloseTo(32.73, 2)
  })

  it('is unknown, not zero, when nothing is tagged', () => {
    // The server serves no figure then; 0% would read as "you chose nothing".
    expect(discretionaryShare({ total: null, spending_total: null })).toBeNull()
  })

  it('is unknown when there is no spending to be a share of', () => {
    // A window whose refunds beat its spending: a share of a net refund is
    // not a fact (`shareOfTotal`).
    expect(discretionaryShare({ total: -40, spending_total: -40 })).toBeNull()
    expect(discretionaryShare({ total: 0, spending_total: 0 })).toBeNull()
  })
})

describe('discretionaryRows', () => {
  const rows = discretionaryRows(GROUPS, 725)

  it('puts each group above its categories, in the served order', () => {
    expect(rows.map((r) => [r.kind, r.label])).toEqual([
      ['group', 'Everyday'],
      ['category', 'Dining Out'],
      ['category', 'Coffee'],
      ['group', 'Fun'],
      ['category', 'Hobbies'],
      ['uncategorized', 'Uncategorized'],
    ])
  })

  it('makes the Uncategorized line one row that opens by "no category"', () => {
    // An empty id list would filter nothing and open the whole window.
    const line = rows.find((r) => r.kind === 'uncategorized')
    expect(line?.target).toEqual({ noCategory: true })
    expect(line?.total).toBe(75)
  })

  it('opens a group by every category under it, and a category by itself', () => {
    expect(rows[0].target).toEqual({ categoryIds: ['c-dining', 'c-coffee'] })
    expect(rows[1].target).toEqual({ categoryIds: ['c-dining'] })
  })

  it('shares the discretionary total, so the groups add to 100', () => {
    const groupShares = rows.filter((r) => r.kind !== 'category').map((r) => r.share ?? 0)
    expect(groupShares.reduce((a, b) => a + b, 0)).toBeCloseTo(100, 10)
    // A category's share is of the whole too, not of its group.
    expect(rows[1].share).toBeCloseTo((450 / 725) * 100, 10)
  })

  it('states no share of a total that is not positive', () => {
    const refunds = discretionaryRows(
      [
        {
          group_id: null,
          group_name: 'Uncategorized',
          total: -20,
          avg_monthly: -20,
          categories: [],
        },
      ],
      -20
    )
    expect(refunds[0].share).toBeNull()
  })
})

describe('discretionaryDrill', () => {
  const rows = discretionaryRows(GROUPS, 725)

  it('always sends the report’s own predicate and window', () => {
    for (const row of rows) {
      const drill = discretionaryDrill(row, WINDOW)
      expect(drill.discretionary).toBe(true)
      expect(drill.scope).toBe('leaf')
      expect([drill.startDate, drill.endDate]).toEqual([WINDOW.startDate, WINDOW.endDate])
    }
  })

  it('opens a category line by its id', () => {
    expect(discretionaryDrill(rows[1], WINDOW)).toMatchObject({
      kind: 'category',
      label: 'Dining Out',
      categoryIds: ['c-dining'],
    })
  })

  it('opens the Uncategorized line by the absence of a category, with no ids', () => {
    const drill = discretionaryDrill(rows[5], WINDOW)
    expect(drill.noCategory).toBe(true)
    expect(drill.categoryIds).toBeUndefined()
  })
})

describe('discretionaryMonthDrill', () => {
  it('opens the whole calendar month of a bar', () => {
    expect(discretionaryMonthDrill('2025-02-01', 'Discretionary · Feb 25')).toEqual({
      kind: 'month',
      label: 'Discretionary · Feb 25',
      scope: 'leaf',
      discretionary: true,
      startDate: '2025-02-01',
      endDate: '2025-02-28',
    })
  })
})
