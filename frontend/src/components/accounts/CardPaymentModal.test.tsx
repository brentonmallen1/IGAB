/**
 * What the payment dialog offers to pay.
 *
 * Set aside is a card's envelope, not a measure of the card, so on a card
 * always paid from funded envelopes it keeps accumulating past the balance.
 * The app's own `over-reserved` scenario settles at 1250 against a bill of 50
 * — and the dialog opened prefilled at $1,250.00, one Enter from a $1,200
 * overpayment, under a preset labelled "Ready to pay".
 *
 * Paying more than is owed is still allowed. It is no longer the prefill, and
 * no longer something the app proposed.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const accounts = vi.hoisted(() => ({ current: [] as unknown[] }))
const cards = vi.hoisted(() => ({ current: [] as unknown[] }))

vi.mock('../../api/accounts', () => ({ useAccounts: () => ({ data: accounts.current }) }))
vi.mock('../../api/budgets', () => ({ useBudgetMonth: () => ({ data: { cards: cards.current } }) }))
vi.mock('../../api/liabilities', () => ({ useLiabilities: () => ({ data: [] }) }))
vi.mock('../../api/transactions', () => ({
  useCreateTransaction: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('../../utils/toastUndo', () => ({ useUndoToast: () => vi.fn() }))

import { CardPaymentModal } from './CardPaymentModal'

/** `balance` is signed as the ledger holds it: negative is owed. */
function setup(balance: number, setAside: number) {
  accounts.current = [
    { id: 'card', name: 'Summit Rewards', on_budget: true, classification: 'liability', balance },
    { id: 'cash', name: 'Harborstone Checking', on_budget: true, classification: 'cash', balance: 4000 },
  ]
  cards.current = [{ account_id: 'card', set_aside: setAside, balance }]
}

function amountBox() {
  return screen.getByLabelText('Amount') as HTMLInputElement
}

beforeEach(async () => {
  await new Promise((r) => setTimeout(r, 0))
  window.history.replaceState(null, '')
})

describe('the amount the card payment dialog opens at', () => {
  it('never opens above what the card owes', () => {
    // The over-reserved scenario, to the cent.
    setup(-50, 1250)
    render(<CardPaymentModal budgetId="b1" accountId="card" onClose={() => {}} />)
    expect(amountBox().value).toBe('50.00')
  })

  it('offers no preset above what the card owes', () => {
    setup(-50, 1250)
    render(<CardPaymentModal budgetId="b1" accountId="card" onClose={() => {}} />)
    for (const el of screen.getAllByRole('button')) {
      const money = el.textContent?.match(/\$([\d,]+\.\d{2})/)
      if (money) expect(Number(money[1].replace(/,/g, ''))).toBeLessThanOrEqual(50)
    }
    expect(screen.queryByText(/1,250/)).toBeNull()
  })

  it('still opens at Set aside when the card owes more than that', () => {
    // The ordinary carrying-a-balance shape: the cap must not clamp it.
    setup(-2600, 350)
    render(<CardPaymentModal budgetId="b1" accountId="card" onClose={() => {}} />)
    expect(amountBox().value).toBe('350.00')
  })

  it('calls the preset Set aside, not Ready to pay', () => {
    setup(-2600, 350)
    render(<CardPaymentModal budgetId="b1" accountId="card" onClose={() => {}} />)
    const presets = screen.getByRole('group', { name: 'Suggested amounts' })
    expect(presets.textContent).toContain('Set aside')
    expect(presets.textContent).not.toContain('Ready to pay')
  })

  it('falls back to the balance when nothing is set aside', () => {
    setup(-120, 0)
    render(<CardPaymentModal budgetId="b1" accountId="card" onClose={() => {}} />)
    expect(amountBox().value).toBe('120.00')
  })
})
