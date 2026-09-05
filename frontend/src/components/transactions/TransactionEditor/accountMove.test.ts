import { describe, expect, it } from 'vitest'
import { accountLockReason, categoryDropNote } from './accountMove'

const MOVABLE = { isReconciled: false, isBankFed: false, isSplitLine: false }

describe('accountLockReason', () => {
  it('lets an ordinary row move', () => {
    expect(accountLockReason(MOVABLE)).toBeNull()
  })

  it('says a bank feed owns which account its row lives in', () => {
    // The server refuses this one (domain/account_move.py): the feed lookup
    // is account-scoped, so it would report the row again in the old account.
    expect(accountLockReason({ ...MOVABLE, isBankFed: true })).toMatch(/bank feed/)
  })

  it('says a reconciled row is vouched for where it is', () => {
    expect(accountLockReason({ ...MOVABLE, isReconciled: true })).toMatch(/statement/)
  })

  it('points a split line at its parent', () => {
    expect(accountLockReason({ ...MOVABLE, isSplitLine: true })).toMatch(/Split lines/)
  })

  it('names the structural reason first when a row has several', () => {
    // A reconciled bank-fed split line has one useful answer, not three.
    expect(accountLockReason({ isReconciled: true, isBankFed: true, isSplitLine: true })).toMatch(
      /Split lines/
    )
  })
})

describe('categoryDropNote', () => {
  it('warns before a move that will clear the category', () => {
    expect(categoryDropNote(false, 'Groceries')).toMatch(/Groceries will be cleared/)
  })

  it('says nothing when the target can hold the category', () => {
    expect(categoryDropNote(true, 'Groceries')).toBeNull()
  })

  it('says nothing when there is no category to lose', () => {
    expect(categoryDropNote(false, null)).toBeNull()
  })
})
