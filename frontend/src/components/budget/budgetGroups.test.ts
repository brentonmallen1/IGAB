import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { renderableCategories, renderableCategoryIds, renderableGroups } from './budgetGroups'

function group(id: string, is_system = false) {
  return { id, budget_id: 'b1', name: id, sort_order: 0, is_hidden: false, is_system, system_key: null }
}

describe('renderableGroups', () => {
  it('leaves the system (Income) group out and keeps the rest in order', () => {
    const groups = [group('income', true), group('bills'), group('wants')]
    expect(renderableGroups(groups).map((g) => g.id)).toEqual(['bills', 'wants'])
  })

  it('renderableCategoryIds follows the groups', () => {
    const groups = [group('income', true), group('bills')]
    const cats = [
      { id: 'inflow', category_group_id: 'income', linked_account_id: null },
      { id: 'rent', category_group_id: 'bills', linked_account_id: null },
    ]
    expect([...renderableCategoryIds(groups, cats)]).toEqual(['rent'])
  })

  it('a card set-aside envelope is not a grid row', () => {
    // The cards section owns it: Balance / Set aside / Uncovered, not
    // assigned/activity/available — and its negative is not overspending.
    const groups = [group('cards'), group('bills')]
    const cats = [
      { id: 'visa', category_group_id: 'cards', linked_account_id: 'acct-1' },
      { id: 'rent', category_group_id: 'bills', linked_account_id: null },
    ]
    expect(renderableCategories(cats).map((c) => c.id)).toEqual(['rent'])
    expect([...renderableCategoryIds(groups, cats)]).toEqual(['rent'])
  })
})

describe('every budget surface draws groups through the one helper', () => {
  // The multi-month sheet used to filter `!g.is_system` inline while the grid
  // filtered nothing, so the two disagreed about whether Income was a row.
  // A second inline copy is how that comes back; this reads the sources so
  // it cannot.
  const surfaces = ['BudgetTable/BudgetTable.tsx', 'MultiMonthSheet/MultiMonthSheet.tsx']
  for (const file of surfaces) {
    it(`${file} imports renderableGroups and has no inline is_system filter`, () => {
      const source = readFileSync(resolve(__dirname, file), 'utf8')
      expect(source).toMatch(/import \{[^}]*renderableGroups[^}]*\} from '\.\.\/budgetGroups'/)
      expect(source).not.toMatch(/!\s*g\.is_system/)
    })
  }
})
