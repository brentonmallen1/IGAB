import { describe, expect, it } from 'vitest'
import { countActiveFilters } from './activeFilters'
import type { ReportFilters } from '../../../stores/reportStore'

const none: ReportFilters = {
  startDate: '2026-01-01',
  endDate: '2026-09-01',
  categoryIds: [],
  tagIds: [],
  filterId: null,
  payeeIds: [],
  accountIds: [],
  viewId: null,
  groupBy: 'group',
} as ReportFilters

describe('countActiveFilters', () => {
  it('is zero with only a range and a rollup, which every report has', () => {
    expect(countActiveFilters(none)).toBe(0)
  })

  it('counts each scope axis once, however many ids it holds', () => {
    expect(countActiveFilters({ ...none, categoryIds: ['a', 'b', 'c'] })).toBe(1)
    expect(countActiveFilters({ ...none, categoryIds: ['a'], payeeIds: ['p'], viewId: 'v' })).toBe(
      3
    )
  })

  it('counts a saved filter and a tag as scope', () => {
    expect(countActiveFilters({ ...none, filterId: 'f', tagIds: ['t'] })).toBe(2)
  })
})
