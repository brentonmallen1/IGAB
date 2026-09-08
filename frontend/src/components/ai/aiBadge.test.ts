import { describe, expect, it } from 'vitest'
import { aiBadgeLabel, aiBadgeState } from './aiBadge'

describe('aiBadgeState', () => {
  it('draws nothing when there is nothing', () => {
    expect(aiBadgeState({ active: 0, needsReview: 0 })).toEqual({
      kind: 'none',
      count: 0,
      working: false,
    })
  })

  it('shows a dot while work is in flight and nothing is waiting', () => {
    expect(aiBadgeState({ active: 2, needsReview: 0 })).toEqual({
      kind: 'working',
      count: 0,
      working: true,
    })
  })

  it('shows the count of what is waiting', () => {
    expect(aiBadgeState({ active: 0, needsReview: 3 })).toEqual({
      kind: 'review',
      count: 3,
      working: false,
    })
  })

  it('lets the count outrank the spinner, and keeps the pulse', () => {
    // The header pill had this the other way round: submitting a second
    // receipt replaced "3 waiting" with "1 processing", hiding the result of
    // the first behind the arrival of the second.
    expect(aiBadgeState({ active: 1, needsReview: 3 })).toEqual({
      kind: 'review',
      count: 3,
      working: true,
    })
  })
})

describe('aiBadgeLabel', () => {
  it('counts in words for a screen reader', () => {
    expect(aiBadgeLabel(aiBadgeState({ active: 0, needsReview: 1 }))).toBe(
      '1 AI transaction to approve'
    )
    expect(aiBadgeLabel(aiBadgeState({ active: 0, needsReview: 4 }))).toBe(
      '4 AI transactions to approve'
    )
  })

  it('says both when both are true', () => {
    expect(aiBadgeLabel(aiBadgeState({ active: 2, needsReview: 4 }))).toBe(
      '4 AI transactions to approve — more still processing'
    )
  })

  it('names the working state', () => {
    expect(aiBadgeLabel(aiBadgeState({ active: 1, needsReview: 0 }))).toBe('AI is processing')
  })

  it('says nothing when there is nothing to say', () => {
    expect(aiBadgeLabel(aiBadgeState({ active: 0, needsReview: 0 }))).toBe('')
  })
})
