import { describe, expect, it } from 'vitest'
import { closedDebtNote, totalLiabilitiesSub } from './liabilitiesView'

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
