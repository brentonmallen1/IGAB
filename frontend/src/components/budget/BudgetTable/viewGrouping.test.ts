import { describe, expect, it } from 'vitest'
import { groupByView, UNASSIGNED_GROUP_ID, visibleCategoryIds } from './viewGrouping'
import type { BudgetView, Category } from '../../../types'

const BUDGET = 'b1'

function cat(id: string, name: string, group = 'real-group'): Category {
  return {
    id,
    category_group_id: group,
    budget_id: BUDGET,
    name,
    subtitle: null,
    sort_order: 0,
    note: null,
    is_hidden: false,
    linked_account_id: null,
    linked_liability_id: null,
    is_assignable: true,
    is_categorizable: true,
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
  }
}

function view(groups: [string, string][], placements: Partial<BudgetView['placements'][0]>[]): BudgetView {
  return {
    id: 'v1',
    budget_id: BUDGET,
    name: 'Need / Want / Save',
    sort_order: 0,
    hide_unassigned: false,
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

describe('groupByView', () => {
  it('puts categories under the view groups, not their own', () => {
    const cats = [cat('c1', 'Rent'), cat('c2', 'Dining'), cat('c3', 'Roth')]
    const v = view(
      [['need', 'Need'], ['want', 'Want'], ['save', 'Save']],
      [
        { category_id: 'c1', group_id: 'need' },
        { category_id: 'c2', group_id: 'want' },
        { category_id: 'c3', group_id: 'save' },
      ]
    )
    const { groups, byGroup } = groupByView(v, cats, BUDGET)

    expect(groups.map((g) => g.name)).toEqual(['Need', 'Want', 'Save'])
    expect(byGroup.get('need')!.map((c) => c.name)).toEqual(['Rent'])
    expect(byGroup.get('save')!.map((c) => c.name)).toEqual(['Roth'])
  })

  it('collects unplaced categories under Unassigned, rendered last', () => {
    const cats = [cat('c1', 'Rent'), cat('c2', 'Something New')]
    const v = view([['need', 'Need']], [{ category_id: 'c1', group_id: 'need' }])

    const { groups, byGroup } = groupByView(v, cats, BUDGET)
    expect(byGroup.get(UNASSIGNED_GROUP_ID)!.map((c) => c.name)).toEqual(['Something New'])
    expect(groups.at(-1)!.name).toBe('Unassigned')
  })

  it('treats a placement with no group as unassigned', () => {
    const v = view([['need', 'Need']], [{ category_id: 'c1', group_id: null }])
    const { byGroup } = groupByView(v, [cat('c1', 'Rent')], BUDGET)
    expect(byGroup.get(UNASSIGNED_GROUP_ID)!.map((c) => c.name)).toEqual(['Rent'])
  })

  it('omits Unassigned entirely when everything is placed', () => {
    const v = view([['need', 'Need']], [{ category_id: 'c1', group_id: 'need' }])
    const { groups, byGroup } = groupByView(v, [cat('c1', 'Rent')], BUDGET)
    expect(groups.map((g) => g.name)).toEqual(['Need'])
    expect(byGroup.has(UNASSIGNED_GROUP_ID)).toBe(false)
  })

  it('drops hidden categories from the grid and their group', () => {
    const cats = [cat('c1', 'Rent'), cat('c2', 'Old Thing')]
    const v = view(
      [['need', 'Need']],
      [
        { category_id: 'c1', group_id: 'need' },
        { category_id: 'c2', group_id: 'need', is_hidden: true },
      ]
    )
    const { byGroup } = groupByView(v, cats, BUDGET)
    expect(byGroup.get('need')!.map((c) => c.name)).toEqual(['Rent'])
  })

  it('a hidden category does not resurface under Unassigned', () => {
    const v = view([['need', 'Need']], [{ category_id: 'c1', is_hidden: true }])
    const { groups, byGroup } = groupByView(v, [cat('c1', 'Rent')], BUDGET)
    expect(byGroup.has(UNASSIGNED_GROUP_ID)).toBe(false)
    expect(groups.map((g) => g.name)).toEqual(['Need'])
  })

  it('orders categories within a group by the view, not the budget', () => {
    const cats = [cat('c1', 'A'), cat('c2', 'B'), cat('c3', 'C')]
    const v = view(
      [['need', 'Need']],
      [
        { category_id: 'c1', group_id: 'need', sort_order: 2 },
        { category_id: 'c2', group_id: 'need', sort_order: 0 },
        { category_id: 'c3', group_id: 'need', sort_order: 1 },
      ]
    )
    const { byGroup } = groupByView(v, cats, BUDGET)
    expect(byGroup.get('need')!.map((c) => c.name)).toEqual(['B', 'C', 'A'])
  })

  it('orders groups by their own sort order', () => {
    const v: BudgetView = {
      ...view([['a', 'Alpha'], ['b', 'Beta']], []),
      groups: [
        { id: 'b', name: 'Beta', sort_order: 0 },
        { id: 'a', name: 'Alpha', sort_order: 1 },
      ],
    }
    expect(groupByView(v, [], BUDGET).groups.map((g) => g.name)).toEqual(['Beta', 'Alpha'])
  })

  it('marks view groups as neither system nor hidden so they render read-only', () => {
    const v = view([['need', 'Need']], [])
    const [g] = groupByView(v, [], BUDGET).groups
    expect(g.is_system).toBe(false)
    expect(g.is_hidden).toBe(false)
    expect(g.budget_id).toBe(BUDGET)
  })

  it('an empty view leaves every category unassigned rather than losing them', () => {
    const cats = [cat('c1', 'Rent'), cat('c2', 'Dining')]
    const { byGroup } = groupByView(view([], []), cats, BUDGET)
    expect(byGroup.get(UNASSIGNED_GROUP_ID)!).toHaveLength(2)
  })

  it('hide_unassigned drops unplaced categories instead of bucketing them', () => {
    const v = {
      ...view([['need', 'Need']], [{ category_id: 'c1', group_id: 'need' }]),
      hide_unassigned: true,
    }
    const cats = [cat('c1', 'Rent'), cat('c2', 'Something New')]
    const { groups, byGroup } = groupByView(v, cats, BUDGET)
    expect(byGroup.has(UNASSIGNED_GROUP_ID)).toBe(false)
    expect(groups.map((g) => g.name)).toEqual(['Need'])
  })

  it('hide_unassigned leaves placed categories alone', () => {
    const v = {
      ...view([['need', 'Need']], [{ category_id: 'c1', group_id: 'need' }]),
      hide_unassigned: true,
    }
    const { byGroup } = groupByView(v, [cat('c1', 'Rent')], BUDGET)
    expect(byGroup.get('need')!.map((c) => c.name)).toEqual(['Rent'])
  })
})

describe('visibleCategoryIds', () => {
  it('includes both placed and unplaced categories', () => {
    const v = view([['g1', 'Need']], [{ category_id: 'c-rent', group_id: 'g1' }])
    const ids = visibleCategoryIds(v, [cat('c-rent', 'Rent'), cat('c-new', 'New')], BUDGET)
    expect(ids).toEqual(new Set(['c-rent', 'c-new']))
  })

  it('excludes what the view hides', () => {
    const v = view(
      [['g1', 'Need']],
      [
        { category_id: 'c-rent', group_id: 'g1' },
        { category_id: 'c-fun', is_hidden: true },
      ]
    )
    const ids = visibleCategoryIds(v, [cat('c-rent', 'Rent'), cat('c-fun', 'Fun')], BUDGET)
    expect(ids).toEqual(new Set(['c-rent']))
  })

  it('excludes the unplaced when hide_unassigned is on', () => {
    const v = view([['g1', 'Need']], [{ category_id: 'c-rent', group_id: 'g1' }])
    v.hide_unassigned = true
    const ids = visibleCategoryIds(v, [cat('c-rent', 'Rent'), cat('c-new', 'New')], BUDGET)
    expect(ids).toEqual(new Set(['c-rent']))
  })
})
