import { describe, it, expect } from 'vitest'
import type { Wish, WishlistProject, WishReach } from '../../../api/wishlist'
import { filterWishes, groupByProject, sortWishes, splitHero, splitProjects } from './wishlistView'

function reach(state: WishReach['state'], months: number | null = null): WishReach {
  return { state, months, date: null, ahead_cost: '0', progress: '0' }
}

function wish(over: Partial<Wish>): Wish {
  return {
    id: over.name ?? 'w',
    project_id: null,
    name: 'W',
    url: null,
    notes: null,
    cost: '100',
    priority: 0,
    is_priority: false,
    status: 'open',
    funding: {
      mode: 'none',
      category_id: null,
      category_name: null,
      inherited: false,
      owns_envelope: false,
      target_date: null,
    },
    cooling_until: null,
    cooling: false,
    last_affirmed_at: null,
    review_due: false,
    done_at: null,
    created_at: '2026-08-01T00:00:00Z',
    reach: null,
    ...over,
  }
}

function project(over: Partial<WishlistProject>): WishlistProject {
  return {
    id: over.name ?? 'p',
    name: 'P',
    category_id: null,
    category_name: null,
    notes: null,
    sort_order: 0,
    summary: {
      item_count: 0,
      open_count: 0,
      total_cost: '0',
      affordable_now: 0,
      funded_by: null,
      state: 'empty',
      complete: false,
    },
    ...over,
  }
}

describe('sortWishes', () => {
  it('reach order is now, then soonest months, then no rate, then unlinked', () => {
    const items = [
      wish({ name: 'unlinked', reach: reach('unlinked') }),
      wish({ name: 'later', reach: reach('months', 8) }),
      wish({ name: 'norate', reach: reach('no_rate') }),
      wish({ name: 'soon', reach: reach('months', 2) }),
      wish({ name: 'now', reach: reach('now', 0) }),
    ]
    expect(sortWishes(items, 'reach').map((w) => w.name)).toEqual([
      'now',
      'soon',
      'later',
      'norate',
      'unlinked',
    ])
  })

  it('other sorts', () => {
    const items = [
      wish({ name: 'b', priority: 2, cost: '5', created_at: '2026-01-01' }),
      wish({ name: 'a', priority: 1, cost: '50', created_at: '2026-03-01' }),
    ]
    expect(sortWishes(items, 'priority').map((w) => w.name)).toEqual(['a', 'b'])
    expect(sortWishes(items, 'cost').map((w) => w.name)).toEqual(['a', 'b'])
    expect(sortWishes(items, 'added').map((w) => w.name)).toEqual(['a', 'b'])
    expect(sortWishes(items, 'name').map((w) => w.name)).toEqual(['a', 'b'])
  })
})

describe('splitHero', () => {
  it('the strip holds only what is pinned, in queue order', () => {
    // Given in display (sorted-by-whatever) order; pins scattered through it.
    const items = [
      wish({ name: 'p4', priority: 4, is_priority: true }),
      wish({ name: 'p1', priority: 1 }),
      wish({ name: 'p3', priority: 3 }),
      wish({ name: 'p0', priority: 0, is_priority: true }),
      wish({ name: 'p2', priority: 2, is_priority: true }),
    ]
    const { hero, rest } = splitHero(items)
    expect(hero.map((w) => w.name)).toEqual(['p0', 'p2', 'p4']) // queue order
    expect(rest.map((w) => w.name)).toEqual(['p1', 'p3']) // given order kept
  })

  it('nothing pinned, nothing floats — the strip is a choice, not a default', () => {
    const items = [2, 0, 1].map((p) => wish({ name: `p${p}`, priority: p }))
    const { hero, rest } = splitHero(items)
    expect(hero).toEqual([])
    expect(rest.map((w) => w.name)).toEqual(['p2', 'p0', 'p1'])
  })
})

describe('filterWishes and groupByProject', () => {
  const trip = project({ name: 'Japan', sort_order: 1 })
  const shop = project({ name: 'Workshop', sort_order: 0 })
  const items = [
    wish({ name: 'Flights', project_id: 'Japan' }),
    wish({ name: 'Bike' }),
    wish({ name: 'Saw', project_id: 'Workshop', notes: 'table saw' }),
  ]

  it('search matches name, notes and project name', () => {
    expect(filterWishes(items, [trip, shop], 'japan').map((w) => w.name)).toEqual(['Flights'])
    expect(filterWishes(items, [trip, shop], 'table').map((w) => w.name)).toEqual(['Saw'])
    expect(filterWishes(items, [trip, shop], '')).toHaveLength(3)
  })

  it('groups in project order with ungrouped wishes last', () => {
    const sections = groupByProject(items, [trip, shop])
    expect(sections.map((s) => s.project?.name ?? null)).toEqual(['Workshop', 'Japan', null])
    expect(sections[2].items.map((w) => w.name)).toEqual(['Bike'])
  })

  it('complete projects go to history', () => {
    const done = project({
      name: 'Done',
      summary: { ...trip.summary, complete: true, state: 'complete' },
    })
    const { active, complete } = splitProjects([trip, done])
    expect(active.map((p) => p.name)).toEqual(['Japan'])
    expect(complete.map((p) => p.name)).toEqual(['Done'])
  })
})
