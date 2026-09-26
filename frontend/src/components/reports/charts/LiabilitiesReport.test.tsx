/**
 * Where the closed-account note sits, what a debt that never pays off reads,
 * and what the page says beside them. The pure sentences are in
 * liabilitiesView.test.ts; this pins the wiring.
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { LiabilitiesReport as LiabilitiesReportData } from '../../../types'

const report = vi.hoisted(() => ({ current: undefined as unknown }))

vi.mock('../../../api/reports', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return {
    ...actual,
    useLiabilitiesReport: () => ({
      data: report.current,
      isLoading: false,
      isError: false,
      refetch: () => {},
    }),
  }
})
vi.mock('../../../api/accountTypes', () => ({ useAccountTypes: () => ({ data: undefined }) }))

import { LiabilitiesReport } from './LiabilitiesReport'

function data(overrides: Partial<LiabilitiesReportData>): LiabilitiesReportData {
  return {
    items: [
      {
        liability_id: 'l1',
        name: 'Jane Doe Personal Loan',
        liability_type: 'personal',
        mode: 'unmanaged',
        current_balance: 1200,
        interest_rate: null,
        baseline_payoff_date: null,
        live_payoff_date: null,
        total_interest_remaining: null,
        baseline_never_pays_off: false,
        never_pays_off: false,
        payoff_basis: null,
        terms_complete: false,
      },
    ],
    total_balance: 1200,
    total_interest_remaining: 0,
    liabilities_missing_terms: 1,
    liabilities_never_paying_off: 0,
    balance_over_time: [],
    closed_with_balance_count: 0,
    closed_with_balance_total: 0,
    ...overrides,
  }
}

function renderIt() {
  return render(
    <MemoryRouter>
      <LiabilitiesReport budgetId="b1" />
    </MemoryRouter>
  )
}

beforeEach(() => {
  report.current = undefined
})

describe('LiabilitiesReport closed-account note', () => {
  it('without closed debt, says every debt and shows no note', () => {
    report.current = data({})
    renderIt()
    expect(screen.getByText('Every debt, cards included')).toBeInTheDocument()
    expect(screen.queryByText(/still owed/)).not.toBeInTheDocument()
  })

  it('sits below the Total Liabilities card, whose label stops saying "every debt"', () => {
    report.current = data({ closed_with_balance_count: 1, closed_with_balance_total: 3000 })
    const { container } = renderIt()
    const note = screen.getByText(/still owed on an account that has been closed/)
    const card = screen.getByText('Total Liabilities')
    // The card comes first in the document, so nothing reads "above" wrongly.
    expect(card.compareDocumentPosition(note) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(note.textContent).not.toMatch(/above/)
    expect(screen.queryByText('Every debt, cards included')).not.toBeInTheDocument()
    expect(screen.getByText('Cards included · excludes 1 closed account')).toBeInTheDocument()
    expect(container.querySelector('.report-section__header')?.textContent).not.toMatch(
      /still owed/
    )
  })

  it('when the only debt is on a closed account, does not say nothing is tracked', () => {
    report.current = data({
      items: [],
      total_balance: 0,
      liabilities_missing_terms: 0,
      closed_with_balance_count: 1,
      closed_with_balance_total: 3000,
    })
    renderIt()
    expect(screen.queryByText(/No liabilities tracked yet/)).not.toBeInTheDocument()
    expect(screen.getByText(/No open liabilities here, but/)).toBeInTheDocument()
  })

  it('an empty report with nothing closed keeps its empty state', () => {
    report.current = data({ items: [], total_balance: 0, liabilities_missing_terms: 0 })
    renderIt()
    expect(screen.getByText(/No liabilities tracked yet/)).toBeInTheDocument()
  })
})

type Item = LiabilitiesReportData['items'][number]

function debt(overrides: Partial<Item>): Item {
  return {
    liability_id: 'l2',
    name: 'Sapphire Visa',
    liability_type: 'credit_card',
    mode: 'unmanaged',
    current_balance: 10000,
    interest_rate: 24,
    baseline_payoff_date: null,
    live_payoff_date: null,
    total_interest_remaining: null,
    baseline_never_pays_off: true,
    never_pays_off: true,
    payoff_basis: 'minimum',
    terms_complete: true,
    ...overrides,
  }
}

function row(name: string): HTMLElement {
  return screen.getByText(name, { selector: '.liabilities-report__name' }).closest('tr')!
}

describe('LiabilitiesReport, a debt that never pays off', () => {
  it('reads "Never at this payment" where its date and interest were $0.00 and —', () => {
    report.current = data({
      items: [debt({})],
      total_balance: 10000,
      liabilities_missing_terms: 0,
      liabilities_never_paying_off: 1,
    })
    renderIt()
    const cells = [...row('Sapphire Visa').querySelectorAll('td')].map((td) => td.textContent)
    // Contractual, and Interest left.
    expect(cells[3]).toBe('Never at this payment')
    expect(cells[5]).toBe('Never at this payment')
    expect(cells[5]).not.toMatch(/\$0\.00/)
  })

  it('says the headline leaves it out', () => {
    report.current = data({
      items: [debt({})],
      total_balance: 10000,
      liabilities_missing_terms: 0,
      liabilities_never_paying_off: 1,
    })
    renderIt()
    expect(
      screen.getByText('At minimum payments · excludes 1 debt that never pays off at its payment')
    ).toBeInTheDocument()
  })

  it('without payment history, names the minimum rather than a pace it does not have', () => {
    report.current = data({ items: [debt({})], liabilities_never_paying_off: 1 })
    renderIt()
    expect(row('Sapphire Visa').textContent).toContain("Won't pay off at the minimum payment")
    expect(row('Sapphire Visa').textContent).not.toContain('current pace')
  })

  it('with a pace that falls short, says current pace — and the minimum’s interest', () => {
    report.current = data({
      items: [
        debt({
          baseline_never_pays_off: false,
          baseline_payoff_date: '2030-01-01',
          total_interest_remaining: 4200,
          payoff_basis: 'observed',
        }),
      ],
      liabilities_never_paying_off: 0,
    })
    renderIt()
    const text = row('Sapphire Visa').textContent
    expect(text).toContain("Won't pay off at current pace")
    expect(text).not.toContain('Never at this payment')
  })
})
