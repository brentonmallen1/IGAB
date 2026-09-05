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

  it("says what the ledger's own interest came to beside the payment", () => {
    // A YNAB loan account carries an interest row a month. The payment is the
    // transfer in (3,000), the interest is that row (1,619) — not 3,000 minus
    // 1,619 fed back into the schedule as the payment.
    render(
      <PayoffPill
        liability={liability({
          average_recent_payment: 3000,
          recent_interest_average: 1619,
          has_live_projection: true,
          live_payoff_date: '2051-03-01',
        })}
      />
    )

    expect(
      screen.getByText(/average \$3,000(\.00)?\/mo, of which ~\$1,619(\.00)? was interest/)
    ).toBeInTheDocument()
    expect(screen.queryByText(/won't pay this off/i)).not.toBeInTheDocument()
  })

  it('says when deposits on the account were not counted as payments', () => {
    render(<PayoffPill liability={liability({ ...blankTerms, uncounted_deposits: 1384.71 })} />)

    expect(screen.getByText(/\$1,384\.71 of plain deposits/)).toBeInTheDocument()
    expect(screen.getByText(/record payments as transfers/)).toBeInTheDocument()
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
