/**
 * Grouping, and the orphan case that made categories vanish.
 *
 * Note what is not tested here: which categories a picker may offer. That rule
 * has one implementation, in the backend (`IS_ASSIGNABLE` / `IS_CATEGORIZABLE`
 * in repositories/category_filters.py), and arrives on the row. The last
 * describe block exists to keep it that way.
 */
import { describe, expect, it } from 'vitest'
import {
  UNGROUPED_LABEL,
  flatCategoryOptions,
  groupedCategorySections,
} from './categoryPickers'
import type { Category, CategoryGroup } from '../types'

function cat(id: string, group: string, over: Partial<Category> = {}): Category {
  return {
    id,
    category_group_id: group,
    budget_id: 'b1',
    name: id.toUpperCase(),
    subtitle: null,
    sort_order: 0,
    note: null,
    is_hidden: false,
    linked_account_id: null,
    linked_liability_id: null,
    is_assignable: true,
    is_categorizable: true,
    ...over,
  } as Category
}

function group(id: string, name: string): CategoryGroup {
  return { id, budget_id: 'b1', name, sort_order: 0, is_hidden: false, is_system: false } as CategoryGroup
}

describe('grouping into sections', () => {
  it('puts each category under its group', () => {
    const sections = groupedCategorySections(
      [cat('a', 'g1'), cat('b', 'g2')],
      [group('g1', 'Bills'), group('g2', 'Fun')]
    )
    expect(sections.map((s) => [s.group.name, s.cats.map((c) => c.id)])).toEqual([
      ['Bills', ['a']],
      ['Fun', ['b']],
    ])
  })

  it('drops groups with nothing in them', () => {
    const sections = groupedCategorySections([cat('a', 'g1')], [group('g1', 'Bills'), group('g2', 'Fun')])
    expect(sections).toHaveLength(1)
  })

  it('keeps a category whose group is missing, under a fallback heading', () => {
    // The bug: the group list is filtered by is_hidden and the category list
    // is not, so a hidden group's categories silently disappeared from the
    // picker while staying live in the data.
    const sections = groupedCategorySections([cat('a', 'g1'), cat('orphan', 'hidden-g')], [group('g1', 'Bills')])
    expect(sections.map((s) => s.group.name)).toEqual(['Bills', UNGROUPED_LABEL])
    expect(sections[1].cats.map((c) => c.id)).toEqual(['orphan'])
  })

  it('sorts the fallback last', () => {
    const sections = groupedCategorySections([cat('orphan', 'gone'), cat('a', 'g1')], [group('g1', 'Bills')])
    expect(sections[sections.length - 1].group.name).toBe(UNGROUPED_LABEL)
  })

  it('handles an empty category list', () => {
    expect(groupedCategorySections([], [group('g1', 'Bills')])).toEqual([])
  })
})

describe('flat options', () => {
  it('carries the group name alongside each category', () => {
    expect(flatCategoryOptions([cat('a', 'g1')], [group('g1', 'Bills')])).toEqual([
      { id: 'a', label: 'A', group: 'Bills' },
    ])
  })

  it('labels an orphan rather than leaving its group blank', () => {
    expect(flatCategoryOptions([cat('a', 'gone')], [])[0].group).toBe(UNGROUPED_LABEL)
  })
})

describe('the server owns eligibility', () => {
  it('exports no eligibility rule', async () => {
    const mod = await import('./categoryPickers')
    expect(Object.keys(mod).sort()).toEqual([
      'UNGROUPED_LABEL',
      'flatCategoryOptions',
      'groupedCategorySections',
    ])
  })

  it('groups whatever it is given, without second-guessing the flags', () => {
    // A category the server marked ineligible is still grouped if a caller
    // passes it — filtering is the caller's one clause, and it reads the field.
    const ineligible = cat('x', 'g1', { is_assignable: false, is_categorizable: false })
    expect(groupedCategorySections([ineligible], [group('g1', 'Bills')])[0].cats).toHaveLength(1)
  })
})
