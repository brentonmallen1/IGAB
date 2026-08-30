/**
 * Saying the rule in words.
 *
 * Two surfaces read this — the terms tile's subtitle and the payoff copy — so
 * the phrasing is pinned here rather than in either of them.
 */
import { describe, expect, it } from 'vitest'
import { describeMinimumRule, minimumDeclines } from './minimumPaymentCopy'

const money = (n: number) => `$${n.toFixed(2)}`

function rule(overrides = {}) {
  return {
    minimum_payment_kind: 'percent_of_balance' as const,
    minimum_payment_percent: 2,
    minimum_payment_floor: 35,
    minimum_payment_plus_interest: false,
    ...overrides,
  }
}

describe('describeMinimumRule', () => {
  it('says the percentage and the floor', () => {
    expect(describeMinimumRule(rule(), money)).toBe('2% of balance, at least $35.00')
  })

  it('says when interest rides on top', () => {
    expect(describeMinimumRule(rule({ minimum_payment_plus_interest: true }), money)).toBe(
      '2% of balance plus interest, at least $35.00',
    )
  })

  it('says nothing for a fixed amount', () => {
    // The figure on screen already says everything there is to say.
    expect(
      describeMinimumRule(
        {
          minimum_payment_kind: 'fixed',
          minimum_payment_percent: null,
          minimum_payment_floor: null,
          minimum_payment_plus_interest: false,
        },
        money,
      ),
    ).toBeNull()
  })

  it('says nothing for a half-entered rule', () => {
    expect(describeMinimumRule(rule({ minimum_payment_percent: null }), money)).toBeNull()
  })

  it('drops the floor clause rather than inventing one', () => {
    expect(describeMinimumRule(rule({ minimum_payment_floor: null }), money)).toBe(
      '2% of balance',
    )
  })
})

describe('minimumDeclines', () => {
  it('is true for a percentage rule', () => {
    expect(minimumDeclines(rule())).toBe(true)
  })

  it('is false for a fixed amount', () => {
    expect(
      minimumDeclines({
        minimum_payment_kind: 'fixed',
        minimum_payment_percent: null,
        minimum_payment_floor: null,
        minimum_payment_plus_interest: false,
      }),
    ).toBe(false)
  })

  it('is false for a rule with no percentage entered', () => {
    expect(minimumDeclines(rule({ minimum_payment_percent: null }))).toBe(false)
  })
})
