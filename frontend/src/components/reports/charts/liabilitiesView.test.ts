import { describe, expect, it } from 'vitest'
import {
  closedDebtNote,
  interestRemainingSub,
  neverPaysOffWarning,
  totalLiabilitiesSub,
} from './liabilitiesView'

describe('closedDebtNote', () => {
  it('says nothing when no closed account owes anything', () => {
    expect(closedDebtNote(0, '$0.00', false)).toBeNull()
    expect(closedDebtNote(0, '$0.00', true)).toBeNull()
  })

  it('names Total Liabilities rather than pointing "above" at a card below it', () => {
    const note = closedDebtNote(1, '$3,000.00', false)!
    expect(note).toContain('$3,000.00 is still owed on an account that has been closed')
    expect(note).toContain('Total Liabilities leaves it out')
    expect(note).toContain('net worth still counts it')
    expect(note).not.toMatch(/above/)
  })

  it('counts several closed accounts', () => {
    expect(closedDebtNote(2, '$4,500.00', false)).toContain('on 2 accounts that have been closed')
  })

  it('in the empty state, does not claim nothing is tracked or refer to a total', () => {
    const note = closedDebtNote(1, '$3,000.00', true)!
    expect(note).toContain('No open liabilities here')
    expect(note).toContain('$3,000.00 is still owed')
    expect(note).not.toMatch(/tracked yet|total/i)
  })
})

describe('totalLiabilitiesSub', () => {
  it('says every debt only while it is every debt', () => {
    expect(totalLiabilitiesSub(0)).toBe('Every debt, cards included')
    expect(totalLiabilitiesSub(1)).toBe('Cards included · excludes 1 closed account')
    expect(totalLiabilitiesSub(3)).toBe('Cards included · excludes 3 closed accounts')
  })
})

describe('interestRemainingSub', () => {
  it('is the minimum-payment figure when every row has a bill', () => {
    expect(interestRemainingSub(0, 0)).toBe('At minimum payments')
  })

  it('names the rows without terms, as it always did', () => {
    expect(interestRemainingSub(2, 0)).toBe('At minimum payments · excludes 2 without terms')
  })

  it('names a debt the minimum never pays off, which used to be added in at $0', () => {
    expect(interestRemainingSub(0, 1)).toBe(
      'At minimum payments · excludes 1 debt that never pays off at its payment'
    )
    expect(interestRemainingSub(0, 2)).toBe(
      'At minimum payments · excludes 2 debts that never pay off at their payments'
    )
  })

  it('names both when both are left out', () => {
    expect(interestRemainingSub(1, 1)).toBe(
      'At minimum payments · excludes 1 without terms · excludes 1 debt that never pays off at its payment'
    )
  })
})

describe('neverPaysOffWarning', () => {
  it('says "current pace" only when there is one', () => {
    expect(neverPaysOffWarning('observed')).toBe("Won't pay off at current pace")
  })

  it('names the minimum when the verdict is the minimum’s — it said "current pace" too', () => {
    expect(neverPaysOffWarning('minimum')).toBe("Won't pay off at the minimum payment")
  })
})
