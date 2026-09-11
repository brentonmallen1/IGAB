/**
 * Where the closed-account note sits, and what the page says beside it.
 * The pure sentences are in liabilitiesView.test.ts; this pins the wiring.
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
        never_pays_off: false,
        terms_complete: false,
      },
    ],
    total_balance: 1200,
    total_interest_remaining: 0,
    liabilities_missing_terms: 1,
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
