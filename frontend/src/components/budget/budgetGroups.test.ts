import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  renderableCategories,
  renderableCategoryIds,
  drawnGroups,
  renderableGroups,
} from './budgetGroups'

function group(id: string, is_system = false, is_card_only = false) {
  return {
    id,
    budget_id: 'b1',
    name: id,
    sort_order: 0,
    is_hidden: false,
    is_system,
    is_card_only,
    system_key: null,
  }
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

describe('drawnGroups', () => {
  it('drops a group the server marked card-only', () => {
    const groups = [group('cards', false, true), group('bills')]
    expect(drawnGroups(groups)?.map((g) => g.id)).toEqual(['bills'])
  })

  it('keeps a group that still has an ordinary category', () => {
    // The server decides this: a group with one non-card row is not card-only,
    // even when that row is hidden — which the client could not have seen,
    // because its category list filters hidden categories out.
    const groups = [group('cards'), group('bills')]
    expect(drawnGroups(groups)?.map((g) => g.id)).toEqual(['cards', 'bills'])
  })

  it('keeps an empty group — a new group needs its header to drop into', () => {
    expect(drawnGroups([group('fresh')])?.map((g) => g.id)).toEqual(['fresh'])
  })

  it('passes undefined through', () => {
    expect(drawnGroups(undefined)).toBeUndefined()
  })

  it('still allows reordering once a card-only group is dropped', () => {
    // The regression this replaced: the gate compared array identity, and this
    // helper only preserved it when nothing was dropped. So a budget that
    // actually had a card group lost its drag handles with nothing to explain
    // it — and on a YNAB import, where "Credit Card Payments" arrives visible
    // and non-system, permanently.
    const groups = [group('cards', false, true), group('bills'), group('wants')]
    const drawn = drawnGroups(groups)
    const visible = drawn
    expect(visible?.length === drawn?.length && (visible?.length ?? 0) > 1).toBe(true)
  })
})

describe('no surface offers a card set-aside envelope', () => {
  // `categoryPickers.ts` records a six-way consolidation onto the served
  // `is_assignable` / `is_categorizable` verdicts. These call sites were
  // missed by it or written after it, and each one offered every card's
  // envelope: the register's own dropdown among them, where filing a row
  // hid the money from the budget completely. Read as source, so a seventh
  // spelling cannot quietly appear.
  const readsServedVerdict: [string, RegExp][] = [
    ['../transactions/TransactionRow/TransactionRow.tsx', /c\.is_categorizable/],
    ['../transactions/SplitTransactionEditor/SplitTransactionEditor.tsx', /c\.is_categorizable/],
    ['../guide/wishlist/ProjectForm.tsx', /c\.is_assignable/],
    ['../guide/wishlist/WishForm.tsx', /c\.is_assignable/],
  ]
  for (const [file, verdict] of readsServedVerdict) {
    it(`${file} filters on the server's verdict`, () => {
      expect(readFileSync(resolve(__dirname, file), 'utf8')).toMatch(verdict)
    })
  }

  const readsTheHelper = [
    'BudgetFilterModal/BudgetFilterModal.tsx',
    'BudgetViewModal/BudgetViewModal.tsx',
    '../reports/ReportFilters/categoryOptions.ts',
    '../imports/ImportReviewDialog/ImportReviewDialog.tsx',
  ]
  for (const file of readsTheHelper) {
    it(`${file} filters through renderableCategories`, () => {
      const source = readFileSync(resolve(__dirname, file), 'utf8')
      expect(source).toMatch(/renderableCategories\(/)
      expect(source).not.toMatch(/linked_account_id\s*[=!]==?\s*null/)
    })
  }
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
