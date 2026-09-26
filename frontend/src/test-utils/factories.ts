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
// an archived one, or a card's envelope, overrides the fields it cares about and
// says so by name.
//
// Three fixtures deliberately do NOT use this: the ones inside `vi.mock` and
// `vi.hoisted` bodies in DeleteCategoryModal, QuickAddSheet.split and
// TransactionEditor. Those run before imports are bound, so they cannot call
// an imported factory at all. They still have to gain a served field by hand —
// which is a limitation of the mock hoisting, not a copy anyone chose.
import type { Category, CategoryBalance, CategoryGroup } from '../types'
import type { Signal } from '../api/guide'
import type { MembershipCategory } from '../api/tags'
import type { SignalKey } from '../content/roadmap'

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
    savings_mode: null,
    savings_role: 'none',
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
    // Both served by the server and required in `CategoryGroup`. Spelled out
    // rather than cast away: a fixture that omits a served field lets a
    // component read `undefined` in a test and a real value in the app.
    is_card_only: false,
    archived_category_count: 0,
    system_key: null,
    ...over,
  }
}

/**
 * A month's balance for one envelope. Defaults describe an ordinary spending
 * envelope with no target: pass the three figures, override the rest by name.
 *
 * An income row is `assigned: null, available: null` — the one shape the
 * summing rule treats differently — so a test that means income has to say so.
 */
export function makeCategoryBalance(over: Partial<CategoryBalance> = {}): CategoryBalance {
  return {
    category_id: 'c1',
    month: '2026-08-01',
    assigned: 0,
    activity: 0,
    available: 0,
    target_status: null,
    needed_this_month: null,
    is_card_payment: false,
    repaid_uncovered_debt: 0,
    credit_overspent: 0,
    ...over,
  } as CategoryBalance
}

/** A Guide signal with nothing detected, tracked and automatic. Three tests
 *  spelled this literal out, and each broke when the server served `fund`. */
export function makeSignal(key: SignalKey, over: Partial<Signal> = {}): Signal {
  return {
    key,
    tracked: true,
    source: 'auto',
    met: null,
    value: null,
    detected_value: null,
    external_value: null,
    external_declared: false,
    external_as_of: null,
    target: null,
    starter_target: null,
    starter_met: null,
    essentials: null,
    fund: null,
    reason: '',
    entities: {},
    gaps: [],
    note: null,
    ...over,
  }
}

/** One row of a tag's checklist: an ordinary spending envelope, not carrying
 *  the tag and not implied onto it. Three test files each spelled this literal
 *  out, and each had to learn the served `implied_by`. */
export function makeMembershipRow(over: Partial<MembershipCategory> = {}): MembershipCategory {
  return {
    id: 'c1',
    name: 'Groceries',
    group_id: 'g-everyday',
    group_name: 'Everyday',
    is_archived: false,
    member: false,
    implied_by: null,
    savings_role: 'none',
    savings_mode: null,
    ...over,
  }
}
