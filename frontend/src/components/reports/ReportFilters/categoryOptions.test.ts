/**
 * The picker must offer exactly what the chart can draw. With a view active
 * that means the view's groups, not the budget's, and nothing the view leaves
 * out — a category selectable here but missing from the chart reads as a
 * broken filter rather than a working view.
 */
import { describe, expect, it } from 'vitest'
import { categoryOptions } from './categoryOptions'
import type { BudgetView, Category } from '../../../types'
import { makeCategory } from '../../../test-utils/factories'

function cat(id: string, name: string, group = 'g-real'): Category {
  return makeCategory({ id, name, category_group_id: group })
}

function view(
  groups: [string, string][],
  placements: Partial<BudgetView['placements'][0]>[],
  hide_unassigned = false
): BudgetView {
  return {
    id: 'v1',
    budget_id: 'b1',
    name: 'Need / Want',
    sort_order: 0,
    hide_unassigned,
    groups: groups.map(([id, name], i) => ({ id, name, sort_order: i })),
    placements: placements.map((p) => ({
      category_id: p.category_id!,
      group_id: p.group_id ?? null,
      sort_order: p.sort_order ?? 0,
      is_hidden: p.is_hidden ?? false,
    })),
    created_at: '',
    updated_at: '',
  }
}

const GROUPS = new Map([['g-real', 'Monthly Bills']])

describe('categoryOptions', () => {
  it('uses the budget groups when no view is active', () => {
    const opts = categoryOptions([cat('c1', 'Rent')], GROUPS, null)
    expect(opts).toEqual([{ id: 'c1', label: 'Rent', group: 'Monthly Bills' }])
  })

  it('buckets by the view groups when one is active', () => {
    const v = view([['need', 'Need']], [{ category_id: 'c1', group_id: 'need' }])
    const opts = categoryOptions([cat('c1', 'Rent')], GROUPS, v)
    expect(opts).toEqual([{ id: 'c1', label: 'Rent', group: 'Need' }])
  })

  it('offers unplaced categories under Unassigned', () => {
    const v = view([['need', 'Need']], [])
    expect(categoryOptions([cat('c1', 'Rent')], GROUPS, v)[0].group).toBe('Unassigned')
  })

  it('does not offer categories the view hides', () => {
    const v = view([['need', 'Need']], [{ category_id: 'c1', is_hidden: true }])
    expect(categoryOptions([cat('c1', 'Rent')], GROUPS, v)).toEqual([])
  })

  it('does not offer unplaced categories when the view hides those', () => {
    const v = view([['need', 'Need']], [{ category_id: 'c1', group_id: 'need' }], true)
    const opts = categoryOptions([cat('c1', 'Rent'), cat('c2', 'Dining')], GROUPS, v)
    expect(opts.map((o) => o.label)).toEqual(['Rent'])
  })

  it('still offers unplaced categories when the view shows them', () => {
    const v = view([['need', 'Need']], [{ category_id: 'c1', group_id: 'need' }], false)
    const opts = categoryOptions([cat('c1', 'Rent'), cat('c2', 'Dining')], GROUPS, v)
    expect(opts.map((o) => o.group)).toEqual(['Need', 'Unassigned'])
  })

  it('hidden categories stay hidden regardless of the view', () => {
    const hidden = { ...cat('c1', 'Old'), is_hidden: true }
    const v = view([['need', 'Need']], [{ category_id: 'c1', group_id: 'need' }])
    expect(categoryOptions([hidden], GROUPS, v)).toEqual([])
  })

  // Composing groupByView rather than restating it: a placement pointing at a
  // group the view no longer has is dropped by the grid, so the picker drops it
  // too. It used to be offered under Unassigned — selectable, and undrawable.
  it('does not offer a category placed in a group the view no longer has', () => {
    const v = view([['need', 'Need']], [{ category_id: 'c1', group_id: 'ghost' }])
    expect(categoryOptions([cat('c1', 'Rent')], GROUPS, v)).toEqual([])
  })
})
