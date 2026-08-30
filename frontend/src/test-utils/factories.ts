// Shared shapes for served API rows, so a field the server adds is added here
// once instead of in every test that builds one by hand.
//
// Seven test files each carried their own `cat()` builder — thirteen literals
// spelling the same object. Adding `is_fundable` to `Category` broke all of
// them at once, which is the cheap version of this lesson: the expensive
// version is a served eligibility flag defaulting differently in two fixtures
// and the tests disagreeing about what the server said.
//
// The defaults describe an ordinary, live spending envelope. A test that wants
// an archived one, or a card envelope, overrides the fields it cares about and
// says so by name.
//
// Three fixtures deliberately do NOT use this: the ones inside `vi.mock` and
// `vi.hoisted` bodies in DeleteCategoryModal, QuickAddSheet.split and
// TransactionEditor. Those run before imports are bound, so they cannot call
// an imported factory at all. They still have to gain a served field by hand —
// which is a limitation of the mock hoisting, not a copy anyone chose.
import type { Category, CategoryGroup } from '../types'

export function makeCategory(over: Partial<Category> = {}): Category {
  return {
    id: 'c1',
    category_group_id: 'g1',
    budget_id: 'b1',
    name: 'Groceries',
    subtitle: null,
    sort_order: 0,
    note: null,
    is_archived: false,
    linked_account_id: null,
    linked_liability_id: null,
    is_assignable: true,
    is_fundable: true,
    is_categorizable: true,
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
    tags: [],
    ...over,
  } as Category
}

export function makeCategoryGroup(over: Partial<CategoryGroup> = {}): CategoryGroup {
  return {
    id: 'g1',
    budget_id: 'b1',
    name: 'Everyday',
    sort_order: 0,
    is_archived: false,
    is_system: false,
    system_key: null,
    ...over,
  } as CategoryGroup
}
