import { describe, expect, it } from 'vitest'
import { registerPayAction } from './payButton'

const acct = (id: string, on_budget: boolean, classification: 'asset' | 'liability' | null) => ({
  id,
  on_budget,
  classification,
})

describe('registerPayAction', () => {
  it('a card register makes a payment; a loan register records one', () => {
    const accounts = [acct('card', true, 'liability'), acct('loan', false, 'liability')]
    expect(registerPayAction(accounts, 'card')).toEqual({ label: 'Make a payment' })
    expect(registerPayAction(accounts, 'loan')).toEqual({ label: 'Record a payment' })
  })

  it('cash and tracking registers pay nobody', () => {
    const accounts = [acct('checking', true, 'asset'), acct('house', false, 'asset')]
    expect(registerPayAction(accounts, 'checking')).toBeNull()
    expect(registerPayAction(accounts, 'house')).toBeNull()
  })

  it('the all-accounts register and an account still loading offer nothing', () => {
    expect(registerPayAction([acct('card', true, 'liability')], null)).toBeNull()
    expect(registerPayAction([], 'card')).toBeNull() // accounts not fetched yet
    expect(registerPayAction([acct('other', true, 'liability')], 'card')).toBeNull()
  })
})
