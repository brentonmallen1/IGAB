/**
 * The review section's holding behaviour. Categorizing a row used to make it
 * leave the section immediately, which is exactly when the user still wants
 * it in reach to add a memo — so the transitions matter more than the
 * steady states.
 *
 * Note what is no longer tested here: whether a row needs a category. That
 * rule has one implementation, in the backend (`NEEDS_CATEGORY`), and its
 * cases live with it — see `test_offbudget_categories.py`. The two tests at
 * the bottom of this file exist to keep it that way.
 */
import { describe, expect, it } from 'vitest'
import { countsAsPendingReview, inReviewSection, nextHeldForReview } from './reviewSection'
import type { Transaction } from '../../../types'

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
    needs_category: true,
    awaiting_approval: false,
    awaiting_category: false,
    ...overrides,
  } as unknown as Transaction
}

describe('holding a row through categorization', () => {
  it('holds an unapproved row that needs a category', () => {
    const held = nextHeldForReview(new Set(), [txn()])
    expect(held.has('t1')).toBe(true)
  })

  it('keeps the row in the section once it gains a category', () => {
    const held = nextHeldForReview(new Set(), [txn()])
    const categorized = txn({ category_id: 'c1', needs_category: false })

    expect(inReviewSection(categorized, held)).toBe(true)
  })

  it('releases the row when it is approved', () => {
    const held = nextHeldForReview(new Set(), [txn()])
    const approved = txn({ category_id: 'c1', needs_category: false, approved: true })
    const after = nextHeldForReview(held, [approved])

    expect(after.has('t1')).toBe(false)
    expect(inReviewSection(approved, after)).toBe(false)
  })

  it('does not hold rows that were already approved', () => {
    const held = nextHeldForReview(new Set(), [txn({ approved: true })])
    expect(held.has('t1')).toBe(false)
  })

  it('still shows an approved row that needs a category', () => {
    expect(inReviewSection(txn({ approved: true }), new Set())).toBe(true)
  })

  it('returns the same set when nothing moved, so state stays stable', () => {
    const held = nextHeldForReview(new Set(), [txn()])
    expect(nextHeldForReview(held, [txn()])).toBe(held)
  })
})

describe('pending rows', () => {
  it('are never held — those have their own section', () => {
    const held = nextHeldForReview(new Set(), [txn({ cleared: 'pending' })])
    expect(held.has('t1')).toBe(false)
  })

  it('never enter the review section, even flagged', () => {
    expect(inReviewSection(txn({ cleared: 'pending' }), new Set(['t1']))).toBe(false)
  })
})

describe('the server owns the rule', () => {
  // These two are the guard rails. They describe rows whose fields would make
  // any locally-rebuilt rule disagree with `needs_category`, and assert the
  // section follows the field. If someone reintroduces a client-side
  // derivation, one of them fails.
  it('does not second-guess a false flag on a row that looks unfiled', () => {
    // Uncategorized, unsplit, not a linked transfer, on a budget account —
    // the old local rule said "needs a category". The server says no, because
    // it can see the payee is a transfer to another on-budget account.
    const unpairedLeg = txn({ category_id: null, transfer_id: null, needs_category: false })
    expect(nextHeldForReview(new Set(), [unpairedLeg]).size).toBe(0)
    expect(inReviewSection(unpairedLeg, new Set())).toBe(false)
  })

  it('does not second-guess a true flag on a row that looks filed', () => {
    // A categorized row the server still wants filed is not a state the
    // register gets to argue with.
    const flagged = txn({ category_id: 'c1', needs_category: true })
    expect(inReviewSection(flagged, new Set())).toBe(true)
  })
})

describe('counting the same population the badge counts', () => {
  // The register auto-paginates while `countsAsPendingReview` finds fewer rows
  // than the badge's total. It reads the badge's own served predicates, so the
  // two range over the same transactions and the loop stops where it should.
  it('counts a transaction waiting to be filed', () => {
    expect(countsAsPendingReview(txn({ awaiting_category: true }))).toBe(true)
  })

  it('counts a transaction waiting to be approved', () => {
    expect(countsAsPendingReview(txn({ approved: false, awaiting_approval: true }))).toBe(true)
  })

  it('ignores one that waits on nothing', () => {
    expect(countsAsPendingReview(txn({ awaiting_approval: false, awaiting_category: false }))).toBe(
      false
    )
  })

  it('counts a split whose line is unfiled, at its parent', () => {
    // The regression: the badge counts this split once, and the parent is the
    // row the register loads. The old mirror read `needs_category`, which is
    // false on a split parent, and paged the whole history looking for the line.
    const split = txn({ is_split: true, needs_category: false, awaiting_category: true })
    expect(countsAsPendingReview(split)).toBe(true)
  })

  it('ignores a pending row, which the server says waits on nothing yet', () => {
    const hold = txn({ cleared: 'pending', approved: false, needs_category: true })
    expect(countsAsPendingReview(hold)).toBe(false)
  })

  it('does not rebuild the rule from approved or needs_category', () => {
    // A split line: unfiled and unapproved in its own columns, waiting on
    // nothing as a transaction — its parent carries the answer.
    const line = txn({ parent_transaction_id: 'p1', approved: false, needs_category: true })
    expect(countsAsPendingReview(line)).toBe(false)
  })
})
