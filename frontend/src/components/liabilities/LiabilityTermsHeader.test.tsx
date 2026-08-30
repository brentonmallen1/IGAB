/**
 * The header is the whole discoverability mechanism: presence, not nagging.
 * A liability-classified account has an APR and a minimum payment whether or
 * not anyone has typed them, so the page keeps a place for them and blank
 * fields do the asking. These pin that it says the right thing in both states
 * — and, in the empty one, that it does not read as a broken or finished debt.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import type { Liability } from '../../api/liabilities'
import { LiabilityTermsHeader } from './LiabilityTermsHeader'

const liabilities: Liability[] = []
vi.mock('../../api/liabilities', () => ({
  useLiabilities: () => ({ data: liabilities }),
}))

function liability(overrides: Partial<Liability> = {}): Liability {
  return {
    id: 'l1',
    budget_id: 'b1',
    name: 'Sapphire Visa',
    liability_type: 'credit_card',
    mode: 'managed',
    linked_account_id: 'acct-1',
    linked_category_id: null,
    current_balance: 420,
    balance_source: 'ledger',
    interest_rate: null,
    minimum_payment: null,
    minimum_payment_kind: 'fixed',
    minimum_payment_percent: null,
    minimum_payment_floor: null,
    minimum_payment_plus_interest: false,
    // Follows minimum_payment: the server computes it from a usable rule, so
    // "no terms entered" means no figure either.
    minimum_payment_due_now: null,
    terms_complete: false,
    origination_date: null,
    original_principal: null,
    monthly_interest_now: null,
    average_recent_payment: null,
    recent_interest_average: null,
    uncounted_deposits: 0,
    implied_term_months: null,
    implied_never_pays_off: null,
    promo_end_date: null,
    promo_deferred_interest: false,
    term_months: null,
    promo_projection: null,
    baseline_payoff_date: null,
    baseline_never_pays_off: false,
    live_payoff_date: null,
    live_never_pays_off: false,
    has_live_projection: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function renderHeader(rows: Liability[], isLoan = false) {
  liabilities.length = 0
  liabilities.push(...rows)
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <LiabilityTermsHeader budgetId="b1" accountId="acct-1" isLoan={isLoan} />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('LiabilityTermsHeader', () => {
  it('keeps a place for terms nobody has entered', () => {
    renderHeader([liability()])

    expect(screen.getAllByText('Not set')).toHaveLength(3)
    expect(screen.getByText('APR')).toBeInTheDocument()
    expect(screen.getByText('Minimum payment')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Add terms/ })).toBeInTheDocument()
  })

  it('does not claim the debt will never pay off while the terms are blank', () => {
    renderHeader([liability()])

    expect(screen.queryByText(/don't cover interest/i)).not.toBeInTheDocument()
  })

  it('asks for what a loan actually needs them for', () => {
    renderHeader([liability()], true)

    expect(screen.getByText(/payoff date, schedule and interest total/)).toBeInTheDocument()
  })

  it('shows the terms and a route to the detail once they are set', () => {
    renderHeader([
      liability({
        interest_rate: 24.99,
        minimum_payment: 95,
        terms_complete: true,
        baseline_payoff_date: '2029-06-15',
      }),
    ])

    expect(screen.getByText('24.99%')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Edit terms/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Payoff detail/ })).toHaveAttribute(
      'href',
      '/liabilities/l1'
    )
    // The hint is for a blank header; with numbers on screen it would nag.
    expect(screen.queryByText(/Add the APR/)).not.toBeInTheDocument()
  })

  it('warns when a real minimum cannot cover interest', () => {
    renderHeader([
      liability({
        interest_rate: 24.99,
        minimum_payment: 5,
        terms_complete: true,
        baseline_never_pays_off: true,
      }),
    ])

    expect(screen.getByText(/don't cover interest/i)).toBeInTheDocument()
  })

  it('surfaces a promo deadline when there is one', () => {
    renderHeader([
      liability({
        interest_rate: 0,
        minimum_payment: 95,
        terms_complete: true,
        promo_end_date: '2027-03-01',
        promo_deferred_interest: true,
      }),
    ])

    expect(screen.getByText('Promo ends (deferred)')).toBeInTheDocument()
  })

  it('renders nothing when the account has no companion', () => {
    const { container } = renderHeader([])

    expect(container).toBeEmptyDOMElement()
  })
})
