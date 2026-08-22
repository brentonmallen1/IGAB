/**
 * Component tests for the report views.
 *
 * Every report API hook is mocked to return one shared, per-test query state,
 * so the suite can drive all twenty report tabs through loading / error /
 * no-data without a server. Recharts renders zero-size under jsdom, so
 * assertions target the surrounding UI (headers, tables, metric cards) —
 * the chart math itself is covered by the pure-function suites.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import type { ComponentType, ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const queryState = vi.hoisted(() => ({
  current: {
    data: undefined as unknown,
    isLoading: false,
    isError: false,
    refetch: () => {},
  },
}))

vi.mock('../../api/reports', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  const mocked: Record<string, unknown> = {}
  for (const key of Object.keys(actual)) {
    mocked[key] = key.startsWith('use') ? () => queryState.current : actual[key]
  }
  return mocked
})
vi.mock('../../api/payees', () => ({ usePayees: () => ({ data: undefined }) }))
vi.mock('../../api/budgets', () => ({ useBudgetMonth: () => ({ data: undefined }) }))
vi.mock('../../api/accountTypes', () => ({ useAccountTypes: () => ({ data: undefined }) }))

import { OverviewReport } from './OverviewReport'
import { AccountCompositionReport } from './charts/AccountCompositionChart'
import { AnomaliesReport } from './charts/AnomaliesReport'
import { BudgetActualReport } from './charts/BudgetActualChart'
import { BurnRateReport } from './charts/BurnRateChart'
import { CashFlowSankeyReport } from './charts/CashFlowSankey'
import { CashProjectionReport } from './charts/CashProjectionReport'
import { DayPatternsReport } from './charts/DayOfWeekChart'
import { TimelineReport } from './charts/EventTimeline'
import { IncomeExpenseReport } from './charts/IncomeExpenseChart'
import { LiabilitiesReport } from './charts/LiabilitiesReport'
import { NetWorthReport } from './charts/NetWorthChart'
import { ParetoReport } from './charts/ParetoChart'
import { PayeeReport } from './charts/PayeeChart'
import { PlanVsRealityReport } from './charts/PlanVsRealityReport'
import { SavingsReport } from './charts/SavingsReport'
import { SavingsRateReport } from './charts/SavingsRateChart'
import { SeasonalityReport } from './charts/SeasonalityHeatmap'
import { SpendingTreemapReport } from './charts/SpendingTreemap'
import { SubscriptionsReport } from './charts/SubscriptionsReport'
import { VarianceReport } from './charts/VarianceChart'
import { VolatilityReport } from './charts/VolatilityChart'

const ALL_REPORTS: [string, ComponentType<{ budgetId: string }>][] = [
  ['Overview', OverviewReport],
  ['NetWorth', NetWorthReport],
  ['AccountComposition', AccountCompositionReport],
  ['Liabilities', LiabilitiesReport],
  ['Savings', SavingsReport],
  ['SavingsRate', SavingsRateReport],
  ['IncomeExpense', IncomeExpenseReport],
  ['BurnRate', BurnRateReport],
  ['CashFlowSankey', CashFlowSankeyReport],
  ['CashProjection', CashProjectionReport],
  ['BudgetActual', BudgetActualReport],
  ['Variance', VarianceReport],
  ['Volatility', VolatilityReport],
  ['Pareto', ParetoReport],
  ['SpendingTreemap', SpendingTreemapReport],
  ['Seasonality', SeasonalityReport],
  ['Subscriptions', SubscriptionsReport],
  ['Anomalies', AnomaliesReport],
  ['PlanVsReality', PlanVsRealityReport],
  ['Payee', PayeeReport],
  ['DayPatterns', DayPatternsReport],
  ['Timeline', TimelineReport],
]

function setQuery(overrides: Partial<typeof queryState.current>) {
  queryState.current = {
    data: undefined,
    isLoading: false,
    isError: false,
    refetch: () => {},
    ...overrides,
  }
}

/** Some report views navigate (e.g. liabilities row click), so render inside a router. */
function renderReport(ui: ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

beforeEach(() => {
  setQuery({})
})

describe.each(ALL_REPORTS)('%s report', (_name, Report) => {
  it('shows the loading state while fetching', () => {
    setQuery({ isLoading: true })
    renderReport(<Report budgetId="b1" />)
    expect(screen.getByText(/Loading/)).toBeInTheDocument()
  })

  it('shows the error state with a working retry on failure', () => {
    const refetch = vi.fn()
    setQuery({ isError: true, refetch })
    renderReport(<Report budgetId="b1" />)
    expect(screen.getByText("Couldn't load this report.")).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(refetch).toHaveBeenCalled()
  })

  it('renders without crashing when the query succeeds with no data', () => {
    setQuery({})
    renderReport(<Report budgetId="b1" />)
    expect(screen.queryByText(/Loading/)).not.toBeInTheDocument()
    expect(screen.queryByText("Couldn't load this report.")).not.toBeInTheDocument()
  })
})

describe('view-hidden note on the spending charts', () => {
  const hiddenData = {
    groups: [
      { id: 'c1', name: 'Dining Out', parent_id: 'g1', parent_name: 'group c', total: 205, count: 3, pct: 100 },
    ],
    total: 205,
    view_hidden_categories: 31,
    view_hidden_total: '14820.45',
  }

  it.each([
    ['Pareto', ParetoReport],
    ['Treemap', SpendingTreemapReport],
  ] as const)('%s states what the view hid', (_name, Report) => {
    setQuery({ data: hiddenData })
    renderReport(<Report budgetId="b1" />)
    expect(screen.getByText(/This view hides 31 categories/)).toBeInTheDocument()
  })

  it.each([
    ['Pareto', ParetoReport],
    ['Treemap', SpendingTreemapReport],
  ] as const)('%s stays quiet when nothing was hidden', (_name, Report) => {
    setQuery({ data: { ...hiddenData, view_hidden_categories: 0, view_hidden_total: '0' } })
    renderReport(<Report budgetId="b1" />)
    expect(screen.queryByText(/This view hides/)).not.toBeInTheDocument()
  })

  it.each([
    ['Pareto', ParetoReport],
    ['Treemap', SpendingTreemapReport],
  ] as const)('%s explains an all-hidden empty state instead of claiming no data', (_name, Report) => {
    setQuery({
      data: { groups: [], total: 0, view_hidden_categories: 34, view_hidden_total: '15025.45' },
    })
    renderReport(<Report budgetId="b1" />)
    expect(
      screen.getByText('Everything with spending in this window is hidden by the current view.')
    ).toBeInTheDocument()
    expect(screen.queryByText('No spending data for this period.')).not.toBeInTheDocument()
  })
})

describe('class-excluded note on the spending charts', () => {
  const dataWithExcluded = {
    groups: [
      { id: 'c1', name: 'Dining Out', parent_id: 'g1', parent_name: 'Bills', total: 205, count: 3, pct: 100 },
    ],
    total: 205,
    view_hidden_categories: 0,
    view_hidden_total: '0',
    class_excluded: [
      { activity_class: 'debt_principal', label: 'Debt payment', categories: 1, total: '275.00' },
    ],
  }

  it.each([
    ['Pareto', ParetoReport],
    ['Treemap', SpendingTreemapReport],
  ] as const)('%s says what a selection excluded and how to add it back', (_name, Report) => {
    setQuery({ data: dataWithExcluded })
    renderReport(<Report budgetId="b1" />)
    expect(screen.getByText(/Not counted as spending here:/)).toBeInTheDocument()
    expect(screen.getByText(/debt payments \(1 category\)/)).toBeInTheDocument()
    expect(screen.getByText(/Include savings & debt payments” to add it/)).toBeInTheDocument()
  })

  it.each([
    ['Pareto', ParetoReport],
    ['Treemap', SpendingTreemapReport],
  ] as const)('%s stays quiet when nothing was class-excluded', (_name, Report) => {
    setQuery({ data: { ...dataWithExcluded, class_excluded: [] } })
    renderReport(<Report budgetId="b1" />)
    expect(screen.queryByText(/Not counted as spending here/)).not.toBeInTheDocument()
  })
})

describe('OverviewReport metric cards', () => {
  it('shows deltas, savings rate, and runway from the dashboard data', () => {
    setQuery({
      data: {
        net_worth: '1100',
        net_worth_prev: '1000',
        burn_rate_30: '900',
        burn_rate_90: '850',
        savings_rate: 0.25,
        days_until_zero: '45.6',
        income_this_month: '4000',
        expenses_this_month: '3000',
        expenses_prev_month: '2500',
        top_categories: [
          { id: 'c1', name: 'Groceries', group_name: 'Everyday', total: '300' },
        ],
      },
    })
    renderReport(<OverviewReport budgetId="b1" />)

    expect(screen.getByText('$1,100.00')).toBeInTheDocument()
    expect(screen.getByText(/\+10\.0%/)).toBeInTheDocument() // net worth delta
    expect(screen.getByText(/\+20\.0%/)).toBeInTheDocument() // spending delta
    expect(screen.getByText('25.0%')).toBeInTheDocument() // savings rate
    expect(screen.getByText('46d')).toBeInTheDocument() // rounded days until zero
    expect(screen.getByText('Groceries')).toBeInTheDocument()
  })
})

describe('SubscriptionsReport table', () => {
  it('shows BOTH the per-charge and normalized monthly columns', () => {
    setQuery({
      data: {
        subscriptions: [
          {
            payee_id: 'p1',
            payee_name: 'Quarterly Gym',
            monthly_amounts: [30, 0, 0, 30],
            total: 120,
            avg_monthly: 10,
            avg_per_charge: 30,
            last_charge_date: '2026-05-01',
            transaction_count: 4,
          },
        ],
        summary: { total_monthly: 10, total_annual: 120, active_count: 1 },
        months: ['2026-02-01', '2026-03-01', '2026-04-01', '2026-05-01'],
      },
    })
    renderReport(<SubscriptionsReport budgetId="b1" />)

    expect(screen.getByText('Per Charge')).toBeInTheDocument()
    expect(screen.getByText('Monthly (effective)')).toBeInTheDocument()
    // $30 per charge but only $10/mo effective — both perspectives visible
    expect(screen.getByText('$30.00')).toBeInTheDocument()
    expect(screen.getAllByText('$10.00').length).toBeGreaterThan(0)
    // projected annual (also the total column — both show $120.00)
    expect(screen.getAllByText('$120.00').length).toBeGreaterThan(0)
  })
})

describe('AnomaliesReport list', () => {
  it('shows the anomaly with its percent change vs baseline', () => {
    setQuery({
      data: {
        anomalies: [
          {
            category_id: 'c1',
            category_name: 'Dining',
            group_name: 'Everyday',
            month: '2026-06-01',
            actual: '300',
            baseline_mean: '100',
            z_score: 10,
            direction: 'high',
            history: ['0', '0', '0', '0', '0', '100', '100', '100', '100', '100', '100', '300'],
          },
        ],
      },
    })
    renderReport(<AnomaliesReport budgetId="b1" />)

    expect(screen.getByText('Dining')).toBeInTheDocument()
    expect(screen.getByText('+200%')).toBeInTheDocument()
  })
})

describe('ParetoReport insight', () => {
  it('computes the 80% concentration from the spending groups', () => {
    setQuery({
      data: {
        groups: [
          { id: 'c1', name: 'Rent', total: '500', count: 1, pct: 50, parent_id: 'g1', parent_name: 'Home' },
          { id: 'c2', name: 'Groceries', total: '300', count: 5, pct: 30, parent_id: 'g2', parent_name: 'Everyday' },
          { id: 'c3', name: 'Gas', total: '150', count: 3, pct: 15, parent_id: 'g2', parent_name: 'Everyday' },
          { id: 'c4', name: 'Fun', total: '50', count: 2, pct: 5, parent_id: 'g2', parent_name: 'Everyday' },
        ],
        total: '1000',
      },
    })
    renderReport(<ParetoReport budgetId="b1" />)

    // total spending card (the drill table's total row shows it too)
    expect(screen.getAllByText('$1,000.00').length).toBeGreaterThan(0)
    // Rent + Groceries reach 80%: 2 of 4 categories = 50% coverage, which is
    // above the 30% adherence threshold, so the spread-thin message shows
    expect(screen.getByText('2 categories')).toBeInTheDocument()
    expect(
      screen.getByText('Spending is spread thin—consider consolidating or reviewing smaller items.')
    ).toBeInTheDocument()
  })
})

describe('PlanVsRealityReport matrix', () => {
  const planData = {
    months: ['2026-06-01', '2026-07-01', '2026-08-01'],
    categories: [
      {
        category_id: 'c1',
        category_name: 'Dining',
        category_group_name: 'Everyday',
        monthly: [
          { month: '2026-06-01', assigned: '100', spent: '140', variance: '-40' },
          { month: '2026-07-01', assigned: '100', spent: '90', variance: '10' },
          { month: '2026-08-01', assigned: '0', spent: '0', variance: '0' },
        ],
        months_over: 1,
        months_active: 2,
        total_assigned: '200',
        total_spent: '230',
        avg_overspend: '40.00',
        chronic: true,
      },
      {
        category_id: 'c2',
        category_name: 'Rent',
        category_group_name: 'Home',
        monthly: [
          { month: '2026-06-01', assigned: '900', spent: '900', variance: '0' },
          { month: '2026-07-01', assigned: '900', spent: '900', variance: '0' },
          { month: '2026-08-01', assigned: '900', spent: '900', variance: '0' },
        ],
        months_over: 0,
        months_active: 3,
        total_assigned: '2700',
        total_spent: '2700',
        avg_overspend: '0',
        chronic: false,
      },
    ],
    total_assigned: '2900',
    total_spent: '2930',
    chronic_count: 1,
  }

  it('renders variance cells, over counts, and the chronic badge', () => {
    setQuery({ data: planData })
    renderReport(<PlanVsRealityReport budgetId="b1" />)

    expect(screen.getByText('Dining')).toBeInTheDocument()
    expect(screen.getByText('Chronic')).toBeInTheDocument()
    expect(screen.getByText('−40')).toBeInTheDocument() // overspent cell
    expect(screen.getByText('+10')).toBeInTheDocument() // underspent cell
    expect(screen.getByText('1/2')).toBeInTheDocument() // months over / active
    expect(screen.getAllByText(/\$2,900\.00/).length).toBeGreaterThan(0)
  })

  it('filters to chronic categories only via the toggle', () => {
    setQuery({ data: planData })
    renderReport(<PlanVsRealityReport budgetId="b1" />)

    fireEvent.click(screen.getByLabelText('Chronic only'))
    expect(screen.getByText('Dining')).toBeInTheDocument()
    expect(screen.queryByText('Rent')).not.toBeInTheDocument()
  })
})

describe('BudgetActualReport values', () => {
  it('renders assigned/spent amounts for each category', () => {
    setQuery({
      data: {
        categories: [
          {
            category_id: 'c1',
            category_name: 'Groceries',
            category_group_name: 'Everyday',
            assigned: '500',
            spent: '450',
            variance: '50',
            variance_pct: 10,
          },
        ],
        total_assigned: '500',
        total_spent: '450',
      },
    })
    renderReport(<BudgetActualReport budgetId="b1" />)

    expect(screen.getByText('Groceries')).toBeInTheDocument()
    expect(screen.getAllByText(/\$500\.00/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/\$450\.00/).length).toBeGreaterThan(0)
  })
})
