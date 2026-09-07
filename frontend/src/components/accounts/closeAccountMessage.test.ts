/**
 * Closing an account moves no money, and the dialog has to say so wherever
 * that matters.
 *
 * It said so for cards and for nothing else, so you could close a checking
 * account holding $400 and get a bare "Close this account?" — while that $400
 * went on funding Ready to Assign from an account no longer in the sidebar.
 *
 * The reason the app does not simply take a closed account off budget is in
 * the module's own docstring: `on_budget` is read at query time, so flipping
 * it would reclassify every historical row. These cases are the cost of that
 * choice being paid honestly.
 */
import { describe, expect, it } from 'vitest'
import { closeAccountMessage, type ClosingAccount } from './closeAccountMessage'

const money = (n: number) => `$${Math.abs(n).toFixed(2)}`

const cash = (balance: number): ClosingAccount => ({
  balance,
  on_budget: true,
  classification: 'asset',
})
const card = (balance: number): ClosingAccount => ({
  balance,
  on_budget: true,
  classification: 'liability',
})
const tracked = (balance: number): ClosingAccount => ({
  balance,
  on_budget: false,
  classification: 'asset',
})

describe('a cash account with money in it', () => {
  it('says what is left and that closing will not move it', () => {
    const message = closeAccountMessage(cash(400), money)
    expect(message).toContain('$400.00')
    expect(message).toContain('Closing moves no money')
    expect(message).toContain('Ready to Assign')
  })

  it('warns on an overdrawn one too', () => {
    // A negative balance is money the budget is counting against you, and
    // hiding the account does not settle it.
    expect(closeAccountMessage(cash(-120), money)).toContain('$120.00')
  })
})

describe('an account with nothing left', () => {
  it('says nothing about an emptied cash account', () => {
    // Closing really is only tidying here. A warning on every close is a
    // warning nobody reads by the time it matters.
    expect(closeAccountMessage(cash(0), money)).toBeNull()
  })

  it('treats float dust from summing a ledger as nothing', () => {
    expect(closeAccountMessage(cash(0.004), money)).toBeNull()
    expect(closeAccountMessage(cash(0.01), money)).not.toBeNull()
  })
})

describe('a card', () => {
  it('names the balance and the set-aside behind it', () => {
    const message = closeAccountMessage(card(-950), money)
    expect(message).toContain('$950.00')
    expect(message).toContain('Credit cards section')
  })

  it('still speaks at zero, because the envelope outlives the balance', () => {
    // The one case where nothing on the account says there is money in play:
    // a settled card whose payment envelope still holds a reserve.
    const message = closeAccountMessage(card(0), money)
    expect(message).toContain('reserved to pay this card')
  })
})

describe('an off-budget account', () => {
  it('says nothing, because no budget money is involved', () => {
    // A brokerage or a loan holds no envelope money whatever its balance —
    // closing one changes no budget figure.
    expect(closeAccountMessage(tracked(52000), money)).toBeNull()
    expect(
      closeAccountMessage(
        { balance: -286000, on_budget: false, classification: 'liability' },
        money
      )
    ).toBeNull()
  })
})
