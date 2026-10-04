import { describe, expect, it } from 'vitest'
import type { ImportHistoryRow } from '../../../api/budgets'
import { groupImportHistory } from './importHistoryGroups'

const row = (group: string, category: string, available: number | null): ImportHistoryRow => ({
  category_group: group,
  category,
  category_id: null,
  assigned: 0,
  activity: 0,
  available,
})

describe('a read-only month, grouped as YNAB showed it', () => {
  it('keeps YNAB’s order of groups and of categories within them', () => {
    const groups = groupImportHistory([
      row('Bills', 'Rent', 0),
      row('Everyday', 'Groceries', -50),
      row('Bills', 'Utilities', 20),
    ])
    expect(groups.map((g) => g.name)).toEqual(['Bills', 'Everyday'])
    expect(groups[0].rows.map((r) => r.category)).toEqual(['Rent', 'Utilities'])
    expect(groups[0].available).toBe(20)
  })

  it('refuses to total a group with an unreadable Available', () => {
    const [bills] = groupImportHistory([row('Bills', 'Rent', 10), row('Bills', 'Water', null)])
    expect(bills.available).toBeNull()
  })
})
