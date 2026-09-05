/**
 * A companion liability lives in its account. The modal used to ask which
 * account a mortgage should be linked to — from the account's own page —
 * and offered Checking and Savings, because nothing filtered the picker.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Liability } from '../../api/liabilities'
import { LiabilitySettingsModal } from './LiabilitySettingsModal'

const accounts = [
  { id: 'chk', name: 'Checking', classification: 'asset', account_type: 'checking' },
  { id: 'loan', name: 'Car Loan', classification: 'liability', account_type: 'auto_loan' },
  { id: 'visa', name: 'Visa', classification: 'liability', account_type: 'credit_card' },
]
const liabilities: Liability[] = []
vi.mock('../../api/accounts', () => ({ useAccounts: () => ({ data: accounts }) }))
vi.mock('../../api/accountTypes', () => ({ useAccountTypes: () => ({ data: [] }) }))
vi.mock('../../api/liabilities', () => ({
  useLiabilities: () => ({ data: liabilities }),
  useCreateLiability: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateLiability: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteLiability: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('../../hooks/useFocusTrap', () => ({ useFocusTrap: () => ({ current: null }) }))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

function companion(overrides: Partial<Liability> = {}): Liability {
  return {
    id: 'l1',
    budget_id: 'b1',
    name: 'Car Loan',
    liability_type: 'auto',
    mode: 'managed',
    linked_account_id: 'loan',
    linked_asset_id: null,
    planned_extra_payment: null,
    linked_category_id: null,
    current_balance: 9000,
    balance_source: 'ledger',
    interest_rate: 6,
    minimum_payment: 400,
    minimum_payment_kind: 'fixed',
    minimum_payment_percent: null,
    minimum_payment_floor: null,
    minimum_payment_plus_interest: false,
    minimum_payment_due_now: 400,
    terms_complete: true,
    origination_date: null,
    original_principal: null,
    monthly_interest_now: 45,
    average_recent_payment: null,
    recent_interest_average: null,
    uncounted_deposits: 0,
    implied_term_months: null,
    implied_never_pays_off: null,
    promo_end_date: null,
    promo_deferred_interest: false,
    term_months: null,
    payment_due_day: null,
    promo_projection: null,
    baseline_payoff_date: '2028-04-15',
    baseline_never_pays_off: false,
    live_payoff_date: null,
    live_never_pays_off: false,
    has_live_projection: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('LiabilitySettingsModal', () => {
  it('shows a companion its account read-only, with no way to move it', () => {
    liabilities.splice(0, liabilities.length, companion())
    render(<LiabilitySettingsModal budgetId="b1" liability={companion()} onClose={() => {}} />)

    const account = screen.getByLabelText('Account') as HTMLInputElement
    expect(account.value).toBe('Car Loan')
    expect(account.readOnly).toBe(true)
    expect(screen.queryByText('Where does the balance come from?')).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Account' })).not.toBeInTheDocument()
  })

  it('offers only liability accounts when creating', () => {
    liabilities.splice(0, liabilities.length, companion())
    render(<LiabilitySettingsModal budgetId="b1" liability={null} onClose={() => {}} />)

    screen.getByRole('radio', { name: /An account in this budget/ }).click()
    const options = Array.from(
      (screen.getByRole('combobox', { name: 'Account' }) as HTMLSelectElement).options
    ).map((o) => o.textContent)
    // Checking is an asset; Car Loan already backs a liability.
    expect(options).toEqual(['Choose an account…', 'Visa'])
  })
})
