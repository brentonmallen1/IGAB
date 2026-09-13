import { describe, expect, it } from 'vitest'
import { activityClassTone } from './activityClassTone'

describe('activityClassTone', () => {
  it('gives a mixed split (null class) the neutral tone, not a guess from its sign', () => {
    // An all-savings split, negative, used to be drawn as a red expense.
    expect(activityClassTone(null)).toBe('neutral')
  })

  it('gives a class it does not know the neutral tone', () => {
    expect(activityClassTone('a_class_added_later')).toBe('neutral')
  })

  it('draws savings and debt principal as savings, whatever the sign of the row', () => {
    // The tone takes no amount at all: a transfer into savings is negative and
    // is still not an expense.
    expect(activityClassTone('savings')).toBe('savings')
    expect(activityClassTone('debt_principal')).toBe('savings')
  })

  it('reads spending, interest and income by class', () => {
    expect(activityClassTone('spending')).toBe('expense')
    expect(activityClassTone('debt_interest')).toBe('expense')
    expect(activityClassTone('income')).toBe('income')
    expect(activityClassTone('transfer_internal')).toBe('neutral')
  })
})
