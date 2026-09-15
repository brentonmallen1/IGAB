/**
 * The Savings report's three sections — Saved, On the way to savings, Sinking
 * funds — each with its own served total and its own empty state. The report
 * adds nothing up: every total on screen is one the server sent.
 */
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { SavingsEnvelope, SavingsReport as SavingsReportData } from '../../../types'

const state = vi.hoisted(() => ({ data: undefined as unknown }))

// Every report hook reads the one state, as reportViews.test.tsx mocks them:
// the range picker reads a hook of its own.
vi.mock('../../../api/reports', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return Object.fromEntries(
    Object.entries(actual).map(([key, value]) => [
      key,
      key.startsWith('use')
        ? () => ({ data: state.data, isLoading: false, isError: false })
        : value,
    ])
  )
})

import { SavingsReport } from './SavingsReport'

const MONTHS = ['2026-06-01', '2026-07-01', '2026-08-01', '2026-09-01']

function envelope(name: string, balance: number, extra: Partial<SavingsEnvelope> = {}) {
  return {
    category_id: name,
    category_name: name,
    group_name: 'Goals',
    monthly_balances: [balance, balance, balance, balance],
    current_balance: balance,
    total_inflow: balance,
    target: null,
    ...extra,
  }
}

const EMPTY: SavingsReportData = {
  saved: {
    total: 0,
    envelopes_total: 0,
    accounts_total: 0,
    monthly_totals: [0, 0, 0, 0],
    envelopes: [],
    accounts: [],
  },
  on_the_way: { total: 0, envelopes: [] },
  sinking_funds: { total: 0, envelopes: [] },
  months: MONTHS,
  drains: { total: 0, moves: [] },
  unrecovered: [],
}

const FULL: SavingsReportData = {
  ...EMPTY,
  saved: {
    total: 3200,
    envelopes_total: 1200,
    accounts_total: 2000,
    monthly_totals: [2800, 2900, 3100, 3200],
    envelopes: [
      envelope('Emergency Fund', 1200, {
        target: {
          type: 'savings_balance',
          amount: 2000,
          target_date: null,
          status: 'underfunded',
          progress: 0.6,
        },
      }),
    ],
    accounts: [
      {
        account_id: 'a1',
        name: 'Harborstone Reserve',
        account_type: 'savings',
        monthly_balances: [1700, 1800, 1900, 2000],
        current_balance: 2000,
      },
    ],
  },
  on_the_way: { total: 400, envelopes: [envelope('Investing', 400)] },
  sinking_funds: {
    total: 900,
    envelopes: [
      envelope('Vacation', 900, {
        target: {
          type: 'savings_balance',
          amount: 1800,
          target_date: '2027-06-01',
          status: 'overfunded',
          progress: 0.5,
        },
      }),
    ],
  },
}

function renderReport(data: SavingsReportData) {
  state.data = data
  return render(
    <MemoryRouter>
      <SavingsReport budgetId="b1" />
    </MemoryRouter>
  )
}

function section(name: string) {
  return screen.getByRole('region', { name })
}

beforeEach(() => {
  state.data = undefined
})

describe('SavingsReport sections', () => {
  it('states each section with its own served total', () => {
    renderReport(FULL)
    const total = (name: string) =>
      section(name).querySelector('.savings-section__total')?.textContent
    expect(total('Saved')).toBe('$3,200.00')
    expect(total('On the way to savings')).toBe('$400.00')
    expect(total('Sinking funds')).toBe('$900.00')
  })

  it('lists envelopes and off-budget accounts under Saved', () => {
    renderReport(FULL)
    const saved = section('Saved')
    expect(within(saved).getByText('Emergency Fund')).toBeInTheDocument()
    expect(within(saved).getByText('Harborstone Reserve')).toBeInTheDocument()
    expect(
      within(saved).getByText(/Envelopes \$1,200\.00 · Accounts \$2,000\.00/)
    ).toBeInTheDocument()
    expect(within(saved).queryByText('Investing')).not.toBeInTheDocument()
  })

  it('shows a sinking fund’s progress toward its target in the page’s words', () => {
    renderReport(FULL)
    const funds = section('Sinking funds')
    expect(within(funds).getByRole('progressbar', { name: '50% of target' })).toBeInTheDocument()
    // The Budget page shows overfunded as funded.
    expect(within(funds).getByText(/50% of \$1,800\.00 by .* · Funded/)).toBeInTheDocument()
  })

  it('gives On the way no target column and no Saved rows', () => {
    renderReport(FULL)
    const onTheWay = section('On the way to savings')
    expect(within(onTheWay).getByText('Investing')).toBeInTheDocument()
    expect(within(onTheWay).queryByRole('progressbar')).not.toBeInTheDocument()
  })

  it('says what fills each empty section', () => {
    renderReport(EMPTY)
    expect(within(section('Saved')).getByText(/Nothing saved here yet/)).toBeInTheDocument()
    expect(
      within(section('On the way to savings')).getByText('No sent-out Savings envelopes.')
    ).toBeInTheDocument()
    expect(within(section('Sinking funds')).getByText(/No sinking funds/)).toBeInTheDocument()
  })
})

describe('SavingsReport before an import', () => {
  // An imported budget whose history could not be walked back from YNAB's
  // figure before August: the page has to say why the line starts late.
  const data: SavingsReportData = {
    ...EMPTY,
    sinking_funds: {
      total: 150,
      envelopes: [envelope('Vacation', 150, { monthly_balances: [null, null, 100, 150] })],
    },
    unrecovered: [
      { category_id: 'Vacation', category_name: 'Vacation', starts_from: '2026-08-01' },
    ],
  }

  it('names the envelope that starts late, and why', () => {
    renderReport(data)
    const note = screen.getByText(/Vacation starts in/)
    expect(note).toHaveTextContent(/doesn.t reproduce YNAB.s balance/)
  })

  it('says nothing when every month has a figure', () => {
    renderReport({ ...data, unrecovered: [] })
    expect(screen.queryByText(/reproduce YNAB/)).not.toBeInTheDocument()
  })
})
