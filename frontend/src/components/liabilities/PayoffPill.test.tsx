/**
 * A liability waiting for its terms must not be described as one that will
 * never pay off. Both states show no payoff date, but they mean opposite
 * things — one is missing input, the other is a warning about the debt — and
 * the fixes differ. These pin that the pill tells them apart.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { PayoffPill } from './PayoffPill'
import type { Liability } from '../../api/liabilities'

function liability(overrides: Partial<Liability> = {}): Liability {
  return {
    id: 'l1',
    budget_id: 'b1',
    name: 'Car Loan',
    liability_type: 'auto',
    mode: 'managed',
    linked_account_id: 'a1',
    linked_category_id: null,
    current_balance: 9000,
    balance_source: 'ledger',
    interest_rate: 6,
    minimum_payment: 400,
    terms_complete: true,
    origination_date: null,
    original_principal: null,
    monthly_interest_now: 45,
    average_recent_payment: null,
    implied_term_months: null,
    implied_never_pays_off: null,
    promo_end_date: null,
    promo_deferred_interest: false,
    term_months: null,
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

const blankTerms = {
  terms_complete: false,
  interest_rate: null,
  minimum_payment: null,
  monthly_interest_now: null,
  baseline_payoff_date: null,
  baseline_never_pays_off: false,
} satisfies Partial<Liability>

describe('PayoffPill', () => {
  it('asks for the terms rather than claiming the debt never pays off', () => {
    render(<PayoffPill liability={liability(blankTerms)} />)

    expect(screen.getByText('No payoff estimate yet')).toBeInTheDocument()
    expect(screen.queryByText(/won't pay this off/i)).not.toBeInTheDocument()
    expect(screen.getByText(/Add the APR and minimum payment/)).toBeInTheDocument()
  })

  it('reports the pace it can see while the terms are blank', () => {
    // Payment history is observed, not projected, so it survives the gap —
    // and it is the most useful thing to show beside an empty form.
    render(<PayoffPill liability={liability({ ...blankTerms, average_recent_payment: 325 })} />)

    expect(screen.getByText(/paying about \$325(\.00)?\/mo/)).toBeInTheDocument()
  })

  it('still calls a cleared debt paid off with no terms on file', () => {
    render(<PayoffPill liability={liability({ ...blankTerms, current_balance: 0 })} />)

    expect(screen.getByText('Paid off')).toBeInTheDocument()
  })

  it('leaves the ordinary contractual state alone', () => {
    render(<PayoffPill liability={liability()} />)

    expect(screen.getByText(/Paid off by/)).toBeInTheDocument()
    expect(screen.queryByText('No payoff estimate yet')).not.toBeInTheDocument()
  })

  it('still warns when a real minimum cannot cover interest', () => {
    render(
      <PayoffPill
        liability={liability({ baseline_never_pays_off: true, baseline_payoff_date: null })}
      />
    )

    expect(screen.getByText("Won't pay off at the minimum payment")).toBeInTheDocument()
  })
})
