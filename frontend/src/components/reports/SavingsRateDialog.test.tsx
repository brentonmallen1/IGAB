/**
 * The savings-rate dialog. The figures are served — the server's agreement
 * tests (test_savings_contributors.py) prove they sum to the cards; these pin
 * what a reader sees and that the dialog asks for the window it was given.
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { SavingsContributors } from '../../api/reports'

const query = vi.hoisted(() => ({
  current: {
    data: undefined as unknown,
    isLoading: false,
    isError: false,
    error: null as unknown,
    refetch: () => {},
  },
  calls: [] as unknown[][],
}))

vi.mock('../../api/reports', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useSavingsContributors: (...args: unknown[]) => {
    query.calls.push(args)
    return query.current
  },
}))

import { useAppStore } from '../../stores/appStore'
import { PRIVACY_MASK } from '../../utils/money'
import { SavingsRateDialog } from './SavingsRateDialog'

/** 5,000 in; 1,000 saved across three places, one of them drawn back out;
 *  500 of debt principal. */
function contributors(overrides: Partial<SavingsContributors> = {}): SavingsContributors {
  return {
    start_date: '2026-03-01',
    end_date: '2026-03-15',
    income: 5000,
    savings: 1000,
    debt_principal: 500,
    savings_contributors: [
      {
        kind: 'account',
        id: 'a1',
        name: 'Brokerage',
        reason: 'transfer_to_tracked_asset',
        reason_label: 'transfer to a tracked account',
        total: 800,
        count: 2,
      },
      {
        kind: 'category',
        id: 'c1',
        name: 'Vacation Fund',
        reason: 'tagged_savings',
        reason_label: 'category tagged Savings',
        total: 300,
        count: 1,
      },
      {
        kind: 'account',
        id: 'a2',
        name: 'Rainy Day Reserve',
        reason: 'transfer_to_tracked_asset',
        reason_label: 'transfer to a tracked account',
        total: -100,
        count: 1,
      },
    ],
    debt_contributors: [
      {
        kind: 'account',
        id: 'a3',
        name: 'Harborstone Mortgage',
        reason: 'transfer_to_tracked_debt',
        reason_label: 'payment to a tracked debt',
        total: 500,
        count: 1,
      },
    ],
    income_sources: [
      { payee_id: 'p1', payee_name: 'Northwind Payserv', total: 4500, count: 2 },
      { payee_id: null, payee_name: 'No payee', total: 500, count: 1 },
    ],
    ...overrides,
  }
}

function setQuery(overrides: Partial<typeof query.current>) {
  query.current = {
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    refetch: () => {},
    ...overrides,
  }
}

function open(props: { rate?: number | null; withDebt?: boolean } = {}) {
  render(
    <SavingsRateDialog
      budgetId="b1"
      startDate="2026-03-01"
      endDate="2026-03-31"
      rate={props.rate === undefined ? 0.2 : props.rate}
      withDebt={props.withDebt ?? false}
      onClose={() => {}}
    />
  )
}

function rows(section: string): string[] {
  const region = screen.getByRole('region', { name: section })
  return [...region.querySelectorAll('.report-detail__row')].map((li) => li.textContent ?? '')
}

function figures(): Record<string, string> {
  return Object.fromEntries(
    [...document.querySelectorAll('.report-detail__figure')].map((row) => [
      row.querySelector('dt')?.textContent,
      row.querySelector('dd')?.textContent,
    ])
  )
}

function sectionOrder(): string[] {
  return [...document.querySelectorAll('.report-detail__heading')].map((h) => h.textContent ?? '')
}

beforeEach(async () => {
  await new Promise((r) => setTimeout(r, 0))
  await new Promise((r) => setTimeout(r, 0))
  window.history.replaceState(null, '')
  query.calls = []
  setQuery({ data: contributors() })
})

afterEach(() => {
  useAppStore.setState({ privacyMode: false })
})

describe('SavingsRateDialog', () => {
  it('asks for the window it was opened with', () => {
    open()
    expect(query.calls.at(-1)).toEqual(['b1', '2026-03-01', '2026-03-31'])
  })

  it('shows the rate, its formula and the three figures', () => {
    open({ rate: 0.2 })
    const dialog = screen.getByRole('dialog', { name: 'Savings rate' })

    expect(within(dialog).getByText('20.0%')).toBeInTheDocument()
    expect(within(dialog).getByText('Saved ÷ Income')).toBeInTheDocument()
    expect(figures()).toEqual({
      Income: '$5,000.00',
      Saved: '$1,000.00',
      'Debt principal': '$500.00',
    })
  })

  it('lists where the savings went with each reason and share, a withdrawal negative', () => {
    open()
    expect(rows('Where the savings went')).toEqual([
      'Brokeragetransfer to a tracked account$800.0080% of savings',
      'Vacation Fundcategory tagged Savings$300.0030% of savings',
      'Rainy Day Reservetransfer to a tracked account-$100.00-10% of savings',
    ])
  })

  it('without debt, puts debt principal after the income as outside the rate', () => {
    open()
    expect(sectionOrder()).toEqual([
      'Where the savings went',
      'Top income sources',
      'Where the debt principal went',
      'What does not count',
    ])
    const debt = screen.getByRole('region', { name: 'Where the debt principal went' })
    expect(debt).toHaveTextContent('Not part of this rate.')
    expect(rows('Where the debt principal went')).toEqual([
      'Harborstone Mortgagepayment to a tracked debt$500.00100% of debt principal',
    ])
  })

  it('with debt, names the wider formula and lists debt principal beside the savings', () => {
    open({ rate: 0.3, withDebt: true })
    const dialog = screen.getByRole('dialog', { name: 'Savings rate (with debt)' })

    expect(within(dialog).getByText('30.0%')).toBeInTheDocument()
    expect(within(dialog).getByText('(Saved + Debt principal) ÷ Income')).toBeInTheDocument()
    expect(sectionOrder().slice(0, 2)).toEqual([
      'Where the savings went',
      'Where the debt principal went',
    ])
    expect(dialog).not.toHaveTextContent('Not part of this rate.')
  })

  it('lists the income sources with their share of income', () => {
    open()
    expect(rows('Top income sources')).toEqual([
      'Northwind Payserv$4,500.0090% of income',
      'No payee$500.0010% of income',
    ])
  })

  it('folds income sources past the fifth so the list still sums to Income', () => {
    const sources = [3000, 800, 500, 300, 200, 150, 50].map((total, i) => ({
      payee_id: `p${i}`,
      payee_name: `Source ${i}`,
      total,
      count: 1,
    }))
    setQuery({ data: contributors({ income: 5000, income_sources: sources }) })
    open()

    const listed = rows('Top income sources')
    expect(listed).toHaveLength(6)
    expect(listed.at(-1)).toBe('2 other sources$200.004% of income')
  })

  it('says what does not count and how to make something count', () => {
    open()
    const note = screen.getByRole('region', { name: 'What does not count' })
    expect(note).toHaveTextContent(/inside a tracked account/)
    expect(note).toHaveTextContent(/between two of your budget accounts/)
    expect(note).toHaveTextContent(/tag the category it leaves from Savings/)
  })

  it('has no rate to explain without income', () => {
    setQuery({
      data: contributors({
        income: 0,
        savings: 0,
        debt_principal: 0,
        savings_contributors: [],
        debt_contributors: [],
        income_sources: [],
      }),
    })
    open({ rate: null })
    const dialog = screen.getByRole('dialog', { name: 'Savings rate' })

    expect(dialog).toHaveTextContent('No income recorded, so there is no rate to explain.')
    expect(within(dialog).queryByText('Saved ÷ Income')).toBeNull()
    expect(dialog).toHaveTextContent('Nothing moved into savings in this period.')
    expect(dialog).not.toHaveTextContent('% of')
  })

  it('shows a loading state while the contributors are fetched', () => {
    setQuery({ isLoading: true })
    open()
    expect(screen.getByRole('dialog', { name: 'Savings rate' })).toHaveTextContent('Loading…')
  })

  it('shows the error state with a working retry', async () => {
    const refetch = vi.fn()
    setQuery({ isError: true, refetch })
    open()
    expect(screen.getByText("Couldn't load this report.")).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(refetch).toHaveBeenCalled()
  })

  it('masks every amount in privacy mode', () => {
    useAppStore.setState({ privacyMode: true })
    open()
    const dialog = screen.getByRole('dialog', { name: 'Savings rate' })
    expect(dialog.textContent).not.toMatch(/\$-?\d/)
    expect(dialog.textContent).toContain(PRIVACY_MASK)
  })
})
