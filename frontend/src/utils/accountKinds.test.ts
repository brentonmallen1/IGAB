import { describe, expect, it } from 'vitest'
import { isCardAccount, isCashAccount, isLiabilityAccount } from './accountKinds'

const acct = (on_budget: boolean, classification: 'asset' | 'liability' | null) => ({
  on_budget,
  classification,
})

describe('accountKinds', () => {
  it('a card is an on-budget liability, by classification not type string', () => {
    expect(isCardAccount(acct(true, 'liability'))).toBe(true)
    expect(isCardAccount(acct(false, 'liability'))).toBe(false) // a loan
    expect(isCardAccount(acct(true, 'asset'))).toBe(false)
  })

  it('cash is on-budget and not a liability — cards partition out exactly', () => {
    expect(isCashAccount(acct(true, 'asset'))).toBe(true)
    expect(isCashAccount(acct(true, null))).toBe(true)
    expect(isCashAccount(acct(true, 'liability'))).toBe(false)
    expect(isCashAccount(acct(false, 'asset'))).toBe(false) // tracking
  })

  it('a liability takes a payment whether on budget (card) or off (loan)', () => {
    expect(isLiabilityAccount(acct(true, 'liability'))).toBe(true)
    expect(isLiabilityAccount(acct(false, 'liability'))).toBe(true)
    expect(isLiabilityAccount(acct(true, 'asset'))).toBe(false)
    expect(isLiabilityAccount(acct(false, null))).toBe(false)
  })
})
