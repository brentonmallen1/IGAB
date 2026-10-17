/**
 * Naming a category for a row: its name, its group, and the hover that tells
 * two same-named envelopes apart.
 */
import { describe, expect, it } from 'vitest'
import {
  UNGROUPED_LABEL,
  UNKNOWN_CATEGORY,
  buildCategoryLabels,
  categoryDisplay,
  categoryNames,
  categoryPath,
  groupHeading,
} from './categoryLabels'
import { flatCategoryOptions } from './categoryPickers'
import { makeCategory, makeCategoryGroup } from '../test-utils/factories'

const holidays = makeCategoryGroup({ id: 'g-hols', name: 'Holidays' })
const birthdays = makeCategoryGroup({ id: 'g-bdays', name: 'Birthdays' })
const giftsHols = makeCategory({ id: 'gifts-hols', name: 'Gifts', category_group_id: 'g-hols' })
const giftsBdays = makeCategory({ id: 'gifts-bdays', name: 'Gifts', category_group_id: 'g-bdays' })

describe('buildCategoryLabels', () => {
  it('tells two envelopes with one name apart by their groups', () => {
    const labels = buildCategoryLabels([giftsHols, giftsBdays], [holidays, birthdays])
    expect(labels.get('gifts-hols')).toEqual({ name: 'Gifts', group: 'Holidays' })
    expect(labels.get('gifts-bdays')).toEqual({ name: 'Gifts', group: 'Birthdays' })
    expect(categoryPath(labels.get('gifts-hols')!)).toBe('Holidays › Gifts')
    expect(categoryPath(labels.get('gifts-bdays')!)).toBe('Birthdays › Gifts')
  })

  it('leaves a missing group null, and the heading falls back', () => {
    // Null, not the fallback: the AI label matcher reads `group`, and a
    // stand-in would let "Gifts (Other)" name a category whose group was
    // merely not loaded.
    const labels = buildCategoryLabels([giftsHols], [])
    expect(labels.get('gifts-hols')).toEqual({ name: 'Gifts', group: null })
    expect(groupHeading(labels.get('gifts-hols')!)).toBe(UNGROUPED_LABEL)
    expect(categoryPath(labels.get('gifts-hols')!)).toBe(`${UNGROUPED_LABEL} › Gifts`)
  })

  it('names an archived category in an archived group like any other', () => {
    // Naming is not choosing. A row filed in an envelope archived since is
    // still filed there, and the register drew "—" for it when it named from
    // the picker's list, which leaves archived categories out.
    const old = makeCategoryGroup({ id: 'g-old', name: 'Hidden Categories', is_archived: true })
    const archived = makeCategory({
      id: 'old-gym',
      name: 'Gym',
      category_group_id: 'g-old',
      is_archived: true,
      is_categorizable: false,
    })
    const labels = buildCategoryLabels([archived], [old])
    expect(categoryDisplay('old-gym', labels)).toEqual({
      name: 'Gym',
      path: 'Hidden Categories › Gym',
    })
  })

  it('agrees with the picker about an orphan heading', () => {
    // The register's hover and the register's picker name the same group.
    const labels = buildCategoryLabels([giftsHols], [])
    const [option] = flatCategoryOptions([giftsHols], [])
    expect(option.group).toBe(groupHeading(labels.get('gifts-hols')!))
  })
})

describe('categoryDisplay', () => {
  const labels = buildCategoryLabels([giftsHols], [holidays])

  it('names a known category with its path', () => {
    expect(categoryDisplay('gifts-hols', labels)).toEqual({
      name: 'Gifts',
      path: 'Holidays › Gifts',
    })
  })

  it('reads an unknown id as a dash, with nothing to hover', () => {
    expect(categoryDisplay('deleted', labels)).toEqual({ name: UNKNOWN_CATEGORY, path: null })
  })

  it('MatchReviewModal: the merged preview dropped a category it could not name', () => {
    // Its detail columns said "—"; its merged preview tested the looked-up
    // name for truth and dropped the Category line, previewing a result with
    // no category while the accept kept the row's. Both read this now.
    expect(categoryDisplay('deleted', labels).name).toBeTruthy()
  })
})

describe('categoryNames', () => {
  it('is the labels without their groups, for the search parser', () => {
    const labels = buildCategoryLabels([giftsHols, giftsBdays], [holidays, birthdays])
    expect(categoryNames(labels)).toEqual(
      new Map([
        ['gifts-hols', 'Gifts'],
        ['gifts-bdays', 'Gifts'],
      ])
    )
  })
})
