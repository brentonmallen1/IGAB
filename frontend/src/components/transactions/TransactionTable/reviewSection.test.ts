/**
 * The review section's holding behaviour. Categorizing a row used to make it
 * leave the section immediately, which is exactly when the user still wants
 * it in reach to add a memo — so the transitions matter more than the
 * steady states.
 */
import { describe, expect, it } from 'vitest'
import { inReviewSection, needsCategory, nextHeldForReview } from './reviewSection'
import type { Transaction } from '../../../types'

const ON_BUDGET = new Set(['a1'])
const OFF_BUDGET_ACCOUNT = 'a2'

function txn(overrides: Partial<Transaction> = {}): Transaction {
  return {
    id: 't1',
    account_id: 'a1',
    date: '2026-08-02',
    amount: -12.5,
    category_id: null,
    transfer_id: null,
    is_split: false,
    cleared: 'uncleared',
    approved: false,
    ...overrides,
  } as unknown as Transaction
}

// payee p-on transfers to an on-budget account, p-off to a tracked one
const TRANSFER_TARGETS = new Map([
  ['p-on', 'a1'],
  ['p-off', OFF_BUDGET_ACCOUNT],
])

describe('needsCategory', () => {
  it('flags an uncategorized row on a budget account', () => {
    expect(needsCategory(txn(), ON_BUDGET)).toBe(true)
  })

  it('ignores rows on off-budget accounts, which do not use categories', () => {
    expect(needsCategory(txn({ account_id: OFF_BUDGET_ACCOUNT }), ON_BUDGET)).toBe(false)
  })

  it('ignores pending, split, transfer and categorized rows', () => {
    expect(needsCategory(txn({ cleared: 'pending' }), ON_BUDGET)).toBe(false)
    expect(needsCategory(txn({ is_split: true }), ON_BUDGET)).toBe(false)
    expect(needsCategory(txn({ transfer_id: 'x' }), ON_BUDGET)).toBe(false)
    expect(needsCategory(txn({ category_id: 'c1' }), ON_BUDGET)).toBe(false)
  })
})

describe('a transfer whose partner never imported', () => {
  // The reported bug: a YNAB export writes legs whose partner never arrives,
  // so `transfer_id` is null. They are still transfers. Before this, a real
  // import drew 930 of them as rows waiting to be filed.
  it('is recognised by its payee, not only by its partner link', () => {
    const leg = txn({ payee_id: 'p-on', transfer_id: null })
    expect(needsCategory(leg, ON_BUDGET, TRANSFER_TARGETS)).toBe(false)
  })

  it('still needs a category when the money leaves the budget', () => {
    // A mortgage payment. Budgeting for it is the whole point.
    const leg = txn({ payee_id: 'p-off', transfer_id: null })
    expect(needsCategory(leg, ON_BUDGET, TRANSFER_TARGETS)).toBe(true)
  })

  it('does not mistake an ordinary payee for a transfer', () => {
    const shop = txn({ payee_id: 'p-shop' })
    expect(needsCategory(shop, ON_BUDGET, TRANSFER_TARGETS)).toBe(true)
  })

  it('treats an unresolvable counterpart as on-budget, like the backend', () => {
    // A linked leg with no transfer payee: nothing says the money left, so
    // it is internal movement rather than something to file.
    const leg = txn({ transfer_id: 'x', payee_id: null })
    expect(needsCategory(leg, ON_BUDGET, TRANSFER_TARGETS)).toBe(false)
  })

  it('keeps an unpaired leg out of the review section entirely', () => {
    const leg = txn({ payee_id: 'p-on', transfer_id: null })
    const held = nextHeldForReview(new Set(), [leg], ON_BUDGET, TRANSFER_TARGETS)
    expect(held.size).toBe(0)
    expect(inReviewSection(leg, ON_BUDGET, held, TRANSFER_TARGETS)).toBe(false)
  })
})

describe('holding a row through categorization', () => {
  it('holds an unapproved uncategorized row', () => {
    const held = nextHeldForReview(new Set(), [txn()], ON_BUDGET)
    expect(held.has('t1')).toBe(true)
  })

  it('keeps the row in the section once it gains a category', () => {
    const held = nextHeldForReview(new Set(), [txn()], ON_BUDGET)
    const categorized = txn({ category_id: 'c1' })

    expect(needsCategory(categorized, ON_BUDGET)).toBe(false)
    expect(inReviewSection(categorized, ON_BUDGET, held)).toBe(true)
  })

  it('releases the row when it is approved', () => {
    const held = nextHeldForReview(new Set(), [txn()], ON_BUDGET)
    const approved = txn({ category_id: 'c1', approved: true })
    const after = nextHeldForReview(held, [approved], ON_BUDGET)

    expect(after.has('t1')).toBe(false)
    expect(inReviewSection(approved, ON_BUDGET, after)).toBe(false)
  })

  it('does not hold rows that were already approved', () => {
    const held = nextHeldForReview(new Set(), [txn({ approved: true })], ON_BUDGET)
    expect(held.has('t1')).toBe(false)
  })

  it('still shows an approved-but-uncategorized row in the section', () => {
    const t = txn({ approved: true })
    expect(inReviewSection(t, ON_BUDGET, new Set())).toBe(true)
  })

  it('returns the same set when nothing moved, so state stays stable', () => {
    const held = nextHeldForReview(new Set(), [txn()], ON_BUDGET)
    expect(nextHeldForReview(held, [txn()], ON_BUDGET)).toBe(held)
  })

  it('never holds a pending row — those have their own section', () => {
    const held = nextHeldForReview(new Set(), [txn({ cleared: 'pending' })], ON_BUDGET)
    expect(held.has('t1')).toBe(false)
  })
})
