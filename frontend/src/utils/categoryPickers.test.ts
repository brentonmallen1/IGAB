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
  filingCategoryOptions,
  flatCategoryOptions,
  groupedCategorySections,
} from './categoryPickers'
import type { Category, CategoryGroup } from '../types'
import { makeCategory } from '../test-utils/factories'

function cat(id: string, group: string, over: Partial<Category> = {}): Category {
  return makeCategory({ id, name: id.toUpperCase(), category_group_id: group, ...over })
}

function group(id: string, name: string): CategoryGroup {
  return {
    id,
    budget_id: 'b1',
    name,
    sort_order: 0,
    is_archived: false,
    is_system: false,
  } as CategoryGroup
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
    const sections = groupedCategorySections(
      [cat('a', 'g1')],
      [group('g1', 'Bills'), group('g2', 'Fun')]
    )
    expect(sections).toHaveLength(1)
  })

  it('keeps a category whose group is missing, under a fallback heading', () => {
    // The bug: the group list is filtered by is_archived and the category list
    // is not, so a hidden group's categories silently disappeared from the
    // picker while staying live in the data.
    const sections = groupedCategorySections(
      [cat('a', 'g1'), cat('orphan', 'hidden-g')],
      [group('g1', 'Bills')]
    )
    expect(sections.map((s) => s.group.name)).toEqual(['Bills', UNGROUPED_LABEL])
    expect(sections[1].cats.map((c) => c.id)).toEqual(['orphan'])
  })

  it('sorts the fallback last', () => {
    const sections = groupedCategorySections(
      [cat('orphan', 'gone'), cat('a', 'g1')],
      [group('g1', 'Bills')]
    )
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
    // The report filter left it blank; the Guide's planner import said
    // "Ungrouped" (unreachable there, since it offers only renderable
    // categories, whose group is always listed). Both read this builder now.
    expect(flatCategoryOptions([cat('a', 'gone')], [])[0].group).toBe(UNGROUPED_LABEL)
  })

  it('keeps the order it is given', () => {
    // The pickers render groups in first-seen order, so the builder must not
    // reorder: the server sorts the category list.
    const opts = flatCategoryOptions(
      [cat('b', 'g2'), cat('a', 'g1'), cat('c', 'g2')],
      [group('g1', 'Bills'), group('g2', 'Fun')]
    )
    expect(opts.map((o) => o.id)).toEqual(['b', 'a', 'c'])
  })
})

/**
 * The builder behind every picker that files a transaction leg. Six hand-made
 * copies of it disagreed; each divergence is a case here, named for the
 * component that got it wrong.
 */
describe('filing pickers', () => {
  const groups = [group('g1', 'Everyday')]

  it('offers only what the server says may be filed to', () => {
    const offered = cat('groceries', 'g1')
    const cardEnvelope = cat('sapphire', 'g-cards', { is_categorizable: false })
    expect(filingCategoryOptions([offered, cardEnvelope], groups)).toEqual([
      { id: 'groceries', label: 'GROCERIES', group: 'Everyday' },
    ])
  })

  it("bulk categorize: a card's envelope is no longer on offer", () => {
    // TransactionTable mapped the raw category list, so the selection bar
    // offered every card's envelope, which the server refuses to file to.
    const cardEnvelope = cat('sapphire', 'g1', {
      linked_account_id: 'acc-card',
      is_assignable: false,
      is_categorizable: false,
    })
    expect(filingCategoryOptions([cardEnvelope], groups)).toEqual([])
  })

  it('register row, split editor and bulk categorize: an orphan gets a heading, not a blank', () => {
    // All three wrote `?? ''`. A live category under a soft-deleted group is
    // categorizable and its group is in no list, so it drew with no header,
    // run into whichever group came before it.
    const orphan = cat('orphan', 'deleted-group')
    expect(filingCategoryOptions([orphan], groups)[0].group).toBe(UNGROUPED_LABEL)
  })

  it('reads the same heading the sectioned pickers draw', () => {
    // Quick-add and the sectioned editors already said UNGROUPED_LABEL; the
    // flat and sectioned pickers now agree about where an orphan sits.
    const orphan = cat('orphan', 'deleted-group')
    const [section] = groupedCategorySections([orphan], groups)
    expect(filingCategoryOptions([orphan], groups)[0].group).toBe(section.group.name)
  })

  it('follows the flag and nothing else', () => {
    // The server decides: a category the client might guess is ineligible
    // (an income category, in a system group) is offered because the server
    // says it may be filed to. That is where a refund or a paycheque goes.
    const income = cat('paycheque', 'g1', { is_assignable: false, is_categorizable: true })
    expect(filingCategoryOptions([income], groups).map((o) => o.id)).toEqual(['paycheque'])
  })
})

describe('the server owns eligibility', () => {
  it('exports no eligibility rule of its own', async () => {
    const mod = await import('./categoryPickers')
    expect(Object.keys(mod).sort()).toEqual([
      'UNGROUPED_LABEL',
      'filingCategoryOptions',
      'flatCategoryOptions',
      'groupedCategorySections',
    ])
  })

  it('groups whatever it is given, without second-guessing the flags', () => {
    // A category the server marked ineligible is still grouped if a caller
    // passes it — filtering is the caller's one clause, and it reads the field.
    const ineligible = cat('x', 'g1', { is_assignable: false, is_categorizable: false })
    expect(groupedCategorySections([ineligible], [group('g1', 'Bills')])[0].cats).toHaveLength(1)
    expect(flatCategoryOptions([ineligible], [group('g1', 'Bills')])).toHaveLength(1)
  })
})
