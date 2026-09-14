import { describe, expect, it } from 'vitest'
import {
  canCountTowardEmergencyFund,
  isCardAccount,
  isCashAccount,
  isLiabilityAccount,
  isTrackedAsset,
} from './accountKinds'

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

  it('only an off-budget asset offers counts-as-savings', () => {
    expect(isTrackedAsset(acct(false, 'asset'))).toBe(true)
    expect(isTrackedAsset(acct(false, null))).toBe(true)
    expect(isTrackedAsset(acct(true, 'asset'))).toBe(false) // on budget: never savings by transfer
    expect(isTrackedAsset(acct(false, 'liability'))).toBe(false) // a loan: debt principal
    expect(isTrackedAsset(acct(true, 'liability'))).toBe(false) // a card
  })

  it('only an off-budget asset that counts as savings can count toward the emergency fund', () => {
    const with_ = (on_budget: boolean, classification: 'asset' | 'liability', saves: boolean) =>
      canCountTowardEmergencyFund({ ...acct(on_budget, classification), counts_as_savings: saves })
    expect(with_(false, 'asset', true)).toBe(true)
    expect(with_(false, 'asset', false)).toBe(false) // a car
    expect(with_(true, 'asset', true)).toBe(false) // its envelopes say what it is for
    expect(with_(false, 'liability', true)).toBe(false) // owed, not held
  })
})
