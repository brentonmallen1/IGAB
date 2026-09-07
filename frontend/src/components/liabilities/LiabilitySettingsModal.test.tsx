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
    typical_recent_payment: null,
    recent_interest_average: null,
    uncounted_deposits: 0,
    implied_term_months: null,
    implied_never_pays_off: null,
    promo_end_date: null,
    promo_deferred_interest: false,
    term_months: null,
    payment_due_day: null,
    payment_components: [],
    payment_components_total: 0,
    full_monthly_payment: null,
    composition_check: 'unknown',
    composition_gap: null,
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
    expect(screen.queryByRole('combobox', { name: 'Account' })).not.toBeInTheDocument()
  })

  it('asks for a balance when creating, and offers no account picker', () => {
    // The picker it replaced could not offer anything. Every
    // liability-classified account is given its companion when it is created,
    // so "liability accounts not already backing a liability" was empty in
    // every budget that has ever existed — and the form then refused to save
    // without a selection from it. A liability created here is one the budget
    // has no account for, which is the only kind this form can make.
    liabilities.splice(0, liabilities.length, companion())
    render(<LiabilitySettingsModal budgetId="b1" liability={null} onClose={() => {}} />)

    expect(screen.getByLabelText('Current balance owed')).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Account' })).not.toBeInTheDocument()
    expect(screen.queryByRole('radio', { name: /An account in this budget/ })).toBeNull()
  })

  it('lets a companion be cut loose from its account', () => {
    // PATCH linked_account_id: null has always worked; the modal refused to
    // send it, so the only route from managed to manual was deleting the
    // account the liability was attached to.
    liabilities.splice(0, liabilities.length, companion())
    render(<LiabilitySettingsModal budgetId="b1" liability={companion()} onClose={() => {}} />)

    expect(screen.getByRole('button', { name: /manage it by hand instead/i })).toBeInTheDocument()
  })
})
