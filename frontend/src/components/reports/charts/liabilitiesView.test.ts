import { describe, expect, it } from 'vitest'
import {
  carryingSub,
  closedDebtNote,
  drawnLiabilities,
  interestRemainingSub,
  paceCell,
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
    expect(interestRemainingSub(0, '$0.00', 0)).toBe('At minimum payments')
  })

  it('says what the rows without terms owe, in dollars — "excludes 2" said nothing', () => {
    expect(interestRemainingSub(2, '$111.00', 0)).toBe(
      'At minimum payments · excludes $111.00 without terms'
    )
  })

  it('names a debt the minimum never pays off, which used to be added in at $0', () => {
    expect(interestRemainingSub(0, '$0.00', 1)).toBe(
      'At minimum payments · excludes 1 debt that never pays off at its payment'
    )
    expect(interestRemainingSub(0, '$0.00', 2)).toBe(
      'At minimum payments · excludes 2 debts that never pay off at their payments'
    )
  })

  it('names both when both are left out', () => {
    expect(interestRemainingSub(1, '$300.00', 1)).toBe(
      'At minimum payments · excludes $300.00 without terms · excludes 1 debt that never pays off at its payment'
    )
  })
})

describe('carryingSub', () => {
  it('counts the rows owing anything', () => {
    expect(carryingSub(4, 7)).toBe('4 carrying a balance')
    expect(carryingSub(0, 2)).toBe('0 carrying a balance')
  })

  it('says all when it is all', () => {
    expect(carryingSub(3, 3)).toBe('All carrying a balance')
    expect(carryingSub(1, 1)).toBe('Carrying a balance')
  })
})

describe('paceCell', () => {
  const month = (d: string) => `<${d}>`
  const base = {
    payoff_basis: null,
    never_pays_off: false,
    live_payoff_date: null,
    pace_missing: null,
  } as const

  it('a pace that pays off gives its month', () => {
    expect(
      paceCell({ ...base, payoff_basis: 'observed', live_payoff_date: '2029-03-01' }, month)
    ).toEqual({ text: '<2029-03-01>', warning: false })
  })

  it('a pace that never pays off warns in the pace’s own words', () => {
    expect(paceCell({ ...base, payoff_basis: 'observed', never_pays_off: true }, month)).toEqual({
      text: "Won't pay off at your pace",
      warning: true,
    })
  })

  it('no pace says why, one reason each — the cell said "—" for all three', () => {
    expect(paceCell({ ...base, pace_missing: 'no_terms' }, month).text).toBe('No terms')
    expect(paceCell({ ...base, pace_missing: 'payments_not_linked' }, month).text).toBe(
      'Payments not linked'
    )
    expect(paceCell({ ...base, pace_missing: 'too_little_history' }, month).text).toBe(
      'Too little history'
    )
    expect(paceCell({ ...base, pace_missing: 'too_little_history' }, month).why).toMatch(
      /two months/
    )
  })

  it('a minimum that never pays off is the other column’s news, not this one’s', () => {
    // It said "Won't pay off at the minimum payment" here, under a heading
    // that promised the pace, for a debt with no pace at all.
    expect(
      paceCell(
        {
          ...base,
          payoff_basis: 'minimum',
          never_pays_off: true,
          pace_missing: 'too_little_history',
        },
        month
      ).text
    ).toBe('Too little history')
  })
})

describe('drawnLiabilities', () => {
  it('leaves out a debt that is zero across the window, and keeps one absent early', () => {
    const items = [{ liability_id: 'paid' }, { liability_id: 'new' }, { liability_id: 'old' }]
    const points: { per_liability: Record<string, number> }[] = [
      { per_liability: { paid: 0, old: 500 } },
      { per_liability: { paid: 0, new: 2000, old: 400 } },
    ]
    expect(drawnLiabilities(items, points).map((i) => i.liability_id)).toEqual(['new', 'old'])
  })
})
