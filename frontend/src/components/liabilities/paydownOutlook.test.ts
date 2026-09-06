/**
 * Which payoff the Liability page leads with.
 *
 * It led with the contractual minimum unconditionally, labelled *At minimum
 * payment* — so a household paying a mortgage plus a separate curtailment
 * every month read two headline numbers describing a repayment nobody was
 * making. The observed pace leads now, and the contractual figure moves to
 * the sub-line rather than vanishing: it is what the loan does if the extra
 * stops.
 */
import { describe, expect, it } from 'vitest'
import type { AmortizationResponse } from '../../api/liabilities'
import { paydownOutlook } from './paydownOutlook'

const money = (n: number) => `$${n.toLocaleString('en-US')}`

function response(over: Partial<AmortizationResponse> = {}): AmortizationResponse {
  return {
    current_balance: 240000,
    terms_complete: true,
    baseline_schedule: Array.from({ length: 300 }, () => ({}) as never),
    baseline_payoff_date: '2051-03-01',
    baseline_never_pays_off: false,
    baseline_total_interest: 190000,
    extra_payment: null,
    curtailment: null,
    extra_schedule: null,
    extra_payoff_date: null,
    extra_never_pays_off: false,
    extra_total_interest: null,
    live_payoff_date: '2044-01-01',
    live_never_pays_off: false,
    live_typical_payment: 2000,
    live_total_interest: 120000,
    live_months: 210,
    history: [],
    ...over,
  }
}

describe('when there is a pace on record', () => {
  it('leads with what you are actually paying', () => {
    const outlook = paydownOutlook(response(), money)
    expect(outlook.basis).toBe('live')
    expect(outlook.interest).toBe(120000)
    expect(outlook.months).toBe(210)
  })

  it('names the pace it assumed, so the number is checkable', () => {
    expect(paydownOutlook(response(), money).interestNote).toContain('$2,000/mo')
  })

  it('keeps the contractual figure on the sub-line rather than hiding it', () => {
    // What the loan does if the extra stops — the reason the extra is worth
    // paying, and a real thing to want to know.
    const outlook = paydownOutlook(response(), money)
    expect(outlook.interestNote).toContain('$190,000 at the minimum')
    expect(outlook.monthsNote).toContain('300 at the minimum')
  })

  it('says so when the minimum alone would never clear the debt', () => {
    const outlook = paydownOutlook(
      response({ baseline_never_pays_off: true, baseline_total_interest: null }),
      money
    )
    expect(outlook.basis).toBe('live')
    expect(outlook.interestNote).toContain("wouldn't cover interest")
  })
})

describe('when there is not', () => {
  it('falls back to the minimum, exactly as before', () => {
    const outlook = paydownOutlook(
      response({ live_months: null, live_total_interest: null, live_typical_payment: null }),
      money
    )
    expect(outlook.basis).toBe('minimum')
    expect(outlook.interest).toBe(190000)
    expect(outlook.months).toBe(300)
    expect(outlook.interestNote).toBe('At the minimum payment')
  })

  it('does not lead with a pace that never clears the debt', () => {
    // The live schedule stops at the cap; its running total is where we gave
    // up counting, not what the loan will cost.
    const outlook = paydownOutlook(
      response({ live_never_pays_off: true, live_months: null, live_total_interest: null }),
      money
    )
    expect(outlook.basis).toBe('minimum')
  })

  it('reports the minimum not covering interest', () => {
    const outlook = paydownOutlook(
      response({
        live_months: null,
        live_total_interest: null,
        baseline_never_pays_off: true,
        baseline_total_interest: null,
      }),
      money
    )
    expect(outlook.interest).toBeNull()
    expect(outlook.monthsNote).toContain("doesn't cover interest")
  })
})

describe('when there is nothing to project from', () => {
  it('asks for the terms while the response is still loading', () => {
    expect(paydownOutlook(undefined, money).basis).toBe('unknown')
  })

  it('asks for the terms when they are not on file', () => {
    const outlook = paydownOutlook(response({ terms_complete: false }), money)
    expect(outlook.basis).toBe('unknown')
    expect(outlook.interest).toBeNull()
    expect(outlook.months).toBeNull()
    expect(outlook.interestNote).toBe('Needs APR and minimum payment')
  })
})
