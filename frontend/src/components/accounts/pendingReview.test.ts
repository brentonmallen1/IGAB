import { describe, expect, it } from 'vitest'
import { reviewBreakdown, reviewPhrase } from './pendingReview'

const none = {
  unapproved_only: 0,
  uncategorized_only: 0,
  both: 0,
  total: 0,
  unapproved: 0,
  uncategorized: 0,
}

describe('reviewPhrase', () => {
  it('counts one and many', () => {
    expect(reviewPhrase(1)).toBe('1 transaction to review')
    expect(reviewPhrase(15)).toBe('15 transactions to review')
  })
})

describe('reviewBreakdown', () => {
  it('names each reason that is not zero, in the dot’s words', () => {
    expect(reviewBreakdown({ ...none, unapproved: 13, uncategorized: 3 })).toBe(
      '13 to approve · 3 to categorize'
    )
    expect(reviewBreakdown({ ...none, unapproved: 4 })).toBe('4 to approve')
    expect(reviewBreakdown({ ...none, uncategorized: 2 })).toBe('2 to categorize')
  })
})
