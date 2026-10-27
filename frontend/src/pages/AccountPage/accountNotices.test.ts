import { describe, expect, it } from 'vitest'
import type { PendingReviewCounts } from '../../api/transactions'
import { accountNotices, duplicatesPhrase, noticesLabel, noticesTone } from './accountNotices'

const review = (over: Partial<PendingReviewCounts> = {}): PendingReviewCounts => ({
  unapproved_only: 0,
  uncategorized_only: 0,
  both: 0,
  total: 0,
  unapproved: 0,
  uncategorized: 0,
  ...over,
})

const fault = { tone: 'fault' as const, text: 'Bank reports $5,570.00 — $18.60 more.' }
const calm = { tone: 'calm' as const, text: 'Bank reports $5,570.00 — not posted yet.' }

describe('accountNotices', () => {
  it('is empty when nothing is waiting', () => {
    expect(accountNotices({ review: review(), duplicates: 0, drift: null })).toEqual([])
    expect(accountNotices({ review: undefined, duplicates: 0, drift: null })).toEqual([])
  })

  it('lists the most pressing first: duplicates, the bank, then rows to review', () => {
    const kinds = accountNotices({
      review: review({ total: 15, unapproved: 13, uncategorized: 3 }),
      duplicates: 2,
      drift: fault,
    }).map((n) => n.kind)
    expect(kinds).toEqual(['duplicates', 'bank', 'review'])
  })

  it('words each kind the way the desktop bands do', () => {
    const [dupes, bank, rows] = accountNotices({
      review: review({ total: 15, unapproved: 13, uncategorized: 3 }),
      duplicates: 2,
      drift: fault,
    })
    expect(dupes.title).toBe('2 possible duplicates')
    // The bank's own sentence, never re-worded: bankDriftNotice is the
    // wording, and it is the part that used to be wrong.
    expect(bank.detail).toBe(fault.text)
    expect(rows.title).toBe('15 transactions to review')
    expect(rows.detail).toBe('13 to approve · 3 to categorize')
  })

  // The split the sidebar's dot makes: an unfiled row leaves the budget
  // wrong, a row to approve only waits on a look.
  it('warns for rows to categorize and informs for rows only to approve', () => {
    const filed = accountNotices({
      review: review({ total: 39, unapproved: 39 }),
      duplicates: 0,
      drift: null,
    })
    expect(filed[0].tone).toBe('info')
    const unfiled = accountNotices({
      review: review({ total: 1, uncategorized: 1 }),
      duplicates: 0,
      drift: null,
    })
    expect(unfiled[0].tone).toBe('warning')
  })

  it('takes the bank tone from the sync verdict, never its own', () => {
    expect(accountNotices({ review: null, duplicates: 0, drift: fault })[0].tone).toBe('warning')
    expect(accountNotices({ review: null, duplicates: 0, drift: calm })[0].tone).toBe('info')
  })
})

describe('noticesTone', () => {
  it('is null when nothing is waiting', () => {
    expect(noticesTone([])).toBeNull()
  })

  it('is the most urgent tone in the list', () => {
    const list = accountNotices({
      review: review({ total: 4, unapproved: 4 }),
      duplicates: 1,
      drift: null,
    })
    expect(noticesTone(list)).toBe('warning')
    expect(noticesTone(list.filter((n) => n.kind === 'review'))).toBe('info')
  })
})

describe('noticesLabel', () => {
  // The pill shows only a number; its name has to say what the number is.
  it('names how many things and what they are', () => {
    const list = accountNotices({
      review: review({ total: 15, unapproved: 15 }),
      duplicates: 2,
      drift: null,
    })
    expect(noticesLabel(list)).toBe(
      '2 things need a look: 2 possible duplicates, 15 transactions to review'
    )
    expect(noticesLabel(list.slice(0, 1))).toBe('1 thing needs a look: 2 possible duplicates')
  })
})

describe('duplicatesPhrase', () => {
  it('counts one and many', () => {
    expect(duplicatesPhrase(1)).toBe('1 possible duplicate')
    expect(duplicatesPhrase(3)).toBe('3 possible duplicates')
  })
})
