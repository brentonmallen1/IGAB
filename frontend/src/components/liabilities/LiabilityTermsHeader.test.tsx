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
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

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
    linked_asset_id: null,
    planned_extra_payment: null,
    linked_category_id: null,
    current_balance: 420,
    balance_source: 'ledger',
    estimated_interest_this_month: null,
    balance_with_estimate: 0,
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
    typical_recent_payment: null,
    recent_interest_average: null,
    uncounted_deposits: 0,
    implied_term_months: null,
    implied_never_pays_off: null,
    promo_end_date: null,
    promo_deferred_interest: false,
    term_months: null,
    payment_due_kind: 'day_of_month',
    payment_due_day: null,
    payment_due_cycle_days: null,
    payment_due_anchor: null,
    payment_components: [],
    payment_components_total: 0,
    full_monthly_payment: null,
    composition_check: 'unknown',
    composition_gap: null,
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

  it('offers no payment button — that action lives in the register toolbar', () => {
    renderHeader([liability()])

    expect(screen.queryByRole('button', { name: /payment/i })).not.toBeInTheDocument()
  })

  describe('when the bill is due', () => {
    // The header reads today's date, so the clock is pinned: a test whose
    // expectations move with the calendar passes for a week and then starts
    // failing on a Tuesday.
    beforeEach(() => {
      vi.useFakeTimers()
      vi.setSystemTime(new Date(2026, 8, 13, 12, 0, 0)) // Sunday 13 Sep 2026
    })
    afterEach(() => {
      vi.useRealTimers()
    })

    it('has no slot at all before a due date is set', () => {
      renderHeader([liability()])

      expect(screen.queryByText('Bill due')).not.toBeInTheDocument()
    })

    it('shows the next date, with the monthly rule under it', () => {
      renderHeader([liability({ payment_due_day: 17 })])

      expect(screen.getByText('Sep 17')).toBeInTheDocument()
      expect(screen.getByText('the 17th of each month')).toBeInTheDocument()
    })

    it('shows the next date a cycle actually lands on, not the anchor', () => {
      // 3 Sep + 31 days. The point of the whole feature: this card's bill is
      // due on the 4th next time and the 5th after that, and no day-of-month
      // spelling could have said so.
      renderHeader([
        liability({
          payment_due_kind: 'cycle_days',
          payment_due_cycle_days: 31,
          payment_due_anchor: '2026-09-03',
        }),
      ])

      expect(screen.getByText('Oct 4')).toBeInTheDocument()
      expect(screen.getByText('every 31 days')).toBeInTheDocument()
    })

    it('says how far off it is once it is close and the card still owes', () => {
      renderHeader([liability({ payment_due_day: 17, current_balance: 420 })])

      expect(screen.getByText('Bill due in 4 days')).toBeInTheDocument()
    })

    it('stays a plain label on a card that owes nothing', () => {
      // A due date on a settled card is a calendar fact, not news.
      renderHeader([liability({ payment_due_day: 17, current_balance: 0 })])

      expect(screen.getByText('Bill due')).toBeInTheDocument()
      expect(screen.queryByText(/in 4 days/)).not.toBeInTheDocument()
    })

    it('stays a plain label while the bill is still weeks off', () => {
      renderHeader([liability({ payment_due_day: 3, current_balance: 420 })])

      expect(screen.getByText('Oct 3')).toBeInTheDocument()
      expect(screen.getByText('Bill due')).toBeInTheDocument()
    })

    it('never shows a bill due date on a loan, even a stale stored one', () => {
      renderHeader([liability({ payment_due_day: 17 })], true)

      expect(screen.queryByText(/Bill due/)).not.toBeInTheDocument()
    })
  })
})
