import { describe, expect, it } from 'vitest'
import { attentionLevel, attentionSummary } from './accountAttention'

const clear = { uncategorized_count: 0, unapproved_count: 0, pending_count: 0 }

describe('attentionLevel', () => {
  it('is nothing on a clear account', () => {
    expect(attentionLevel(clear)).toBeNull()
  })

  it('wants the person for a row to file', () => {
    expect(attentionLevel({ ...clear, uncategorized_count: 1 })).toBe('review')
  })

  // The case the old count badge missed: it counted uncategorized rows only,
  // so an account full of bank rows to approve looked clear.
  it('wants the person for a row to approve', () => {
    expect(attentionLevel({ ...clear, unapproved_count: 4 })).toBe('review')
  })

  it('is muted for rows that are only on their way', () => {
    expect(attentionLevel({ ...clear, pending_count: 2 })).toBe('pending')
  })

  it('shows the most urgent when both are true', () => {
    expect(attentionLevel({ ...clear, pending_count: 2, unapproved_count: 1 })).toBe('review')
  })
})

describe('attentionSummary', () => {
  it('names each part that is not zero', () => {
    expect(
      attentionSummary({ uncategorized_count: 3, unapproved_count: 5, pending_count: 2 })
    ).toBe('3 to categorize · 5 to approve · 2 pending')
  })

  it('leaves out the zeros', () => {
    expect(attentionSummary({ ...clear, pending_count: 1 })).toBe('1 pending')
  })
})
