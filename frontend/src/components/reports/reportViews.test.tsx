/**
 * Component tests for the report views.
 *
 * Every report API hook is mocked to return one shared, per-test query state,
 * so the suite can drive all twenty report tabs through loading / error /
 * no-data without a server. Recharts renders zero-size under jsdom, so
 * assertions target the surrounding UI (headers, tables, metric cards) —
 * the chart math itself is covered by the pure-function suites.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import type { ComponentType, ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const queryState = vi.hoisted(() => ({
  current: {
    data: undefined as unknown,
    isLoading: false,
    isError: false,
    refetch: () => {},
  },
}))

/** Every call each report hook received, by hook name — so a test can check
 *  what a chart ASKED for, not only what it drew from the shared state. */
const hookCalls = vi.hoisted(() => new Map<string, unknown[][]>())

vi.mock('../../api/reports', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  const mocked: Record<string, unknown> = {}
  for (const key of Object.keys(actual)) {
    mocked[key] = key.startsWith('use')
      ? (...args: unknown[]) => {
          hookCalls.set(key, [...(hookCalls.get(key) ?? []), args])
          return queryState.current
        }
      : actual[key]
  }
  return mocked
})
vi.mock('../../api/payees', () => ({ usePayees: () => ({ data: undefined }) }))
vi.mock('../../api/budgets', () => ({ useBudgetMonth: () => ({ data: undefined }) }))
vi.mock('../../api/accountTypes', () => ({ useAccountTypes: () => ({ data: undefined }) }))
// The Counting line reads its own query; pickerSurfaces.test.tsx covers it.
vi.mock('../../api/emergencyFund', () => ({
  useEmergencyFund: () => ({ data: undefined }),
  useSetEmergencyFund: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

import { useReportStore } from '../../stores/reportStore'
import { useAppStore } from '../../stores/appStore'
import { PRIVACY_MASK } from '../../utils/money'
import { ifIncomeStopped, overviewRunway, runwayFigure } from '../../test-utils/runwayFixtures'
import { CostOfLivingReport } from './charts/CostOfLivingReport'
import { DiscretionaryReport } from './charts/DiscretionaryReport'
import { EssentialsReport } from './charts/EssentialsReport'
import { EmergencyCoverageReport } from './charts/EmergencyCoverageReport'
import { WishlistDisciplineReport } from './charts/WishlistDisciplineReport'
import { OverviewReport } from './OverviewReport'
import { AccountCompositionReport } from './charts/AccountCompositionChart'
import { AnomaliesReport } from './charts/AnomaliesReport'
import { BurnRateReport } from './charts/BurnRateChart'
import { CashFlowSankeyReport } from './charts/CashFlowSankey'
import { CashProjectionReport } from './charts/CashProjectionReport'
import { DayPatternsReport } from './charts/DayOfWeekChart'
import { TimelineReport } from './charts/EventTimeline'
import { IncomeExpenseReport } from './charts/IncomeExpenseChart'
import { IncomeSourcesReport } from './charts/IncomeSourcesReport'
import { LiabilitiesReport } from './charts/LiabilitiesReport'
import { NetWorthReport } from './charts/NetWorthChart'
import { ParetoReport } from './charts/ParetoChart'
import { PayeeReport } from './charts/PayeeChart'
import { PlanVsSpentReport } from './charts/PlanVsSpentReport'
import { SavingsReport } from './charts/SavingsReport'
import { SavingsRateReport } from './charts/SavingsRateChart'
import { SeasonalityReport } from './charts/SeasonalityHeatmap'
import { SpendingTreemapReport } from './charts/SpendingTreemap'
import { SpendingBreakdownReport } from './charts/SpendingBreakdownReport'
import { SpendingTrendsReport } from './charts/SpendingTrendsReport'
import { SubscriptionsReport } from './charts/SubscriptionsReport'
import { VolatilityReport } from './charts/VolatilityChart'
import { today } from '../../utils/dates'

const ALL_REPORTS: [string, ComponentType<{ budgetId: string }>][] = [
  ['Overview', OverviewReport],
  ['CostOfLiving', CostOfLivingReport],
  ['Discretionary', DiscretionaryReport],
  ['Essentials', EssentialsReport],
  ['EmergencyCoverage', EmergencyCoverageReport],
  ['WishlistDiscipline', WishlistDisciplineReport],
  ['NetWorth', NetWorthReport],
  ['AccountComposition', AccountCompositionReport],
  ['Liabilities', LiabilitiesReport],
  ['Savings', SavingsReport],
  ['SavingsRate', SavingsRateReport],
  ['IncomeExpense', IncomeExpenseReport],
  ['BurnRate', BurnRateReport],
  ['CashFlowSankey', CashFlowSankeyReport],
  ['CashProjection', CashProjectionReport],
  ['PlanVsSpent', PlanVsSpentReport],
  ['Volatility', VolatilityReport],
  ['Pareto', ParetoReport],
  ['SpendingTreemap', SpendingTreemapReport],
  ['SpendingBreakdown', SpendingBreakdownReport],
  ['SpendingTrends', SpendingTrendsReport],
  ['Seasonality', SeasonalityReport],
  ['Subscriptions', SubscriptionsReport],
  ['Anomalies', AnomaliesReport],
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

/** The cells of the table row whose text includes `label`. */
function cellsOf(label: string): string[] {
  const row = screen.getByText(label).closest('tr')
  return Array.from(row?.querySelectorAll('td') ?? []).map((td) => td.textContent ?? '')
}

/** What one metric card says: its value and sub-line, read inside the card
 *  named `label` — not anywhere on a page that may print the same figure in
 *  a table or legend. */
function card(label: string): { value: string; sub: string } {
  const el = screen.getByText(label, { selector: '.metric-card__label' }).closest('.metric-card')
  return {
    value: el?.querySelector('.metric-card__value')?.textContent ?? '',
    sub: el?.querySelector('.metric-card__sub')?.textContent ?? '',
  }
}

beforeEach(() => {
  setQuery({})
  hookCalls.clear()
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

/** The spending charts that take a view, and so can be told what it hid.
 *  Spending Trends takes no view. */
const VIEW_CHARTS = [
  ['Pareto', ParetoReport],
  ['Treemap', SpendingTreemapReport],
  ['Breakdown', SpendingBreakdownReport],
] as const

describe('view-hidden note on the spending charts', () => {
  const hiddenData = {
    groups: [
      {
        id: 'c1',
        name: 'Dining Out',
        parent_id: 'g1',
        parent_name: 'group c',
        total: 205,
        count: 3,
        pct: 100,
      },
    ],
    total: 205,
    view_hidden_categories: 31,
    view_hidden_total: 14820.45,
  }

  it.each(VIEW_CHARTS)('%s states what the view hid', (_name, Report) => {
    setQuery({ data: hiddenData })
    renderReport(<Report budgetId="b1" />)
    expect(screen.getByText(/This view hides 31 categories/)).toBeInTheDocument()
  })

  it.each(VIEW_CHARTS)('%s stays quiet when nothing was hidden', (_name, Report) => {
    setQuery({ data: { ...hiddenData, view_hidden_categories: 0, view_hidden_total: '0' } })
    renderReport(<Report budgetId="b1" />)
    expect(screen.queryByText(/This view hides/)).not.toBeInTheDocument()
  })

  it.each(VIEW_CHARTS)(
    '%s explains an all-hidden empty state instead of claiming no data',
    (_name, Report) => {
      setQuery({
        data: { groups: [], total: 0, view_hidden_categories: 34, view_hidden_total: '15025.45' },
      })
      renderReport(<Report budgetId="b1" />)
      expect(
        screen.getByText('Everything with spending in this window is hidden by the current view.')
      ).toBeInTheDocument()
      expect(screen.queryByText('No spending data for this period.')).not.toBeInTheDocument()
    }
  )
})

/** Every spending chart with the "Include savings & debt payments" toggle. */
const TOGGLE_CHARTS = [...VIEW_CHARTS, ['Trends', SpendingTrendsReport]] as const

describe('class-excluded note on the spending charts', () => {
  // One payload in both shapes — the grouped rollup (Pareto, Treemap,
  // Breakdown) and the monthly series (Trends) — since every hook in this
  // suite serves the same data.
  const dataWithExcluded = {
    groups: [
      {
        id: 'c1',
        name: 'Dining Out',
        parent_id: 'g1',
        parent_name: 'Bills',
        total: 205,
        count: 3,
        pct: 100,
      },
    ],
    months: ['2026-08-01'],
    series: [
      {
        id: 'c1',
        name: 'Dining Out',
        group_id: 'g1',
        group_name: 'Bills',
        monthly: [205],
        total: 205,
      },
    ],
    monthly_totals: [205],
    total: 205,
    view_hidden_categories: 0,
    view_hidden_total: '0',
    class_excluded: [
      { activity_class: 'debt_principal', label: 'Debt payment', categories: 1, total: 275.0 },
      { activity_class: 'savings', label: 'Savings', categories: 2, total: 101.0 },
    ],
    filter_unavailable: false,
  }

  it.each(TOGGLE_CHARTS)(
    '%s says what a selection excluded and how to add it back',
    (_name, Report) => {
      setQuery({ data: dataWithExcluded })
      renderReport(<Report budgetId="b1" />)
      expect(screen.getByText(/Not counted as spending here:/)).toBeInTheDocument()
      expect(screen.getByText(/debt payments \(1 category\)/)).toBeInTheDocument()
      // "Savings" must not pluralise into "savingss".
      expect(screen.getByText(/of savings \(2 categories\)/)).toBeInTheDocument()
      // Breakdown drew the toggle yet told the note it had none, so the
      // remedy never showed beside the checkbox that performs it.
      expect(screen.getByText(/Include savings & debt payments” to add it/)).toBeInTheDocument()
    }
  )

  it.each(TOGGLE_CHARTS)('%s stays quiet when nothing was class-excluded', (_name, Report) => {
    setQuery({ data: { ...dataWithExcluded, class_excluded: [] } })
    renderReport(<Report budgetId="b1" />)
    expect(screen.queryByText(/Not counted as spending here/)).not.toBeInTheDocument()
  })

  it.each(TOGGLE_CHARTS)('%s draws the shared toggle, not a copy of it', (_name, Report) => {
    // Breakdown and Trends kept inline checkboxes beside the shared one, and
    // the copies had already lost its explanation.
    setQuery({ data: dataWithExcluded })
    renderReport(<Report budgetId="b1" />)
    const label = screen.getByRole('checkbox', { name: 'Include savings & debt payments' })
    expect(label.nextElementSibling).toHaveAttribute(
      'title',
      expect.stringMatching(/isn.t spending/)
    )
  })
})

describe('a deleted saved filter', () => {
  // Every report whose response declares `filter_unavailable`. Declaring the
  // field put nothing on screen: the timeline never read it, so a deleted
  // filter drew "No transactions for this period." and nothing else.
  const FILTER_SCOPED = [
    ...TOGGLE_CHARTS,
    ['DayPatterns', DayPatternsReport],
    ['Timeline', TimelineReport],
  ] as const

  // Empty in every shape these reports read, since one payload serves all.
  const lost = {
    groups: [],
    months: [],
    series: [],
    monthly_totals: [],
    total: 0,
    days: [],
    transactions: [],
    counted_classes: [],
    window_start: '2026-08-01',
    window_end: '2026-08-31',
    view_hidden_categories: 0,
    view_hidden_total: '0',
    class_excluded: [],
    filter_unavailable: true,
  }

  it.each(FILTER_SCOPED)('%s says the filter is gone', (_name, Report) => {
    setQuery({ data: lost })
    renderReport(<Report budgetId="b1" />)
    expect(screen.getByText(/That saved filter no longer exists/)).toBeInTheDocument()
    // Trends once said the opposite of what the server does.
    expect(screen.queryByText(/showing everything/i)).toBeNull()
  })

  it.each(FILTER_SCOPED)('%s says nothing while the filter exists', (_name, Report) => {
    setQuery({ data: { ...lost, filter_unavailable: false } })
    renderReport(<Report budgetId="b1" />)
    expect(screen.queryByText(/saved filter no longer exists/)).toBeNull()
  })

  it('does not call a report empty that a category beside the filter still fills', () => {
    // The scope is the union of categories, tags and the filter. A missing
    // filter drops its own share; Groceries picked beside it still draws, so
    // "this report has nothing to show" was false above a drawn chart.
    setQuery({
      data: {
        ...lost,
        groups: [
          {
            id: 'c1',
            name: 'Groceries',
            parent_id: 'g1',
            parent_name: 'Everyday',
            total: 120,
            count: 2,
            pct: 100,
          },
        ],
        total: 120,
      },
    })
    renderReport(<SpendingBreakdownReport budgetId="b1" />)
    expect(screen.getByText(/nothing it named is included here/)).toBeInTheDocument()
    expect(screen.queryByText(/nothing to show/)).toBeNull()
  })
})

describe('treemap group-by fallback', () => {
  it('draws group tiles — and says so — when the stored mode is payee', () => {
    useReportStore.getState().setFilters({ groupBy: 'payee' })
    try {
      setQuery({
        data: {
          groups: [
            {
              id: 'c1',
              name: 'Dining',
              parent_id: 'g1',
              parent_name: 'Everyday',
              total: 205,
              count: 3,
              pct: 100,
            },
          ],
          total: 205,
          view_hidden_categories: 0,
          view_hidden_total: '0',
          class_excluded: [],
        },
      })
      renderReport(<SpendingTreemapReport budgetId="b1" />)
      // The breadcrumb only exists in group mode; before the resolver the
      // payee mode landed here by accident with Payee still highlighted.
      expect(screen.getByText('All Groups')).toBeInTheDocument()
      expect(
        screen.getByText('Click a group to drill down into its categories.')
      ).toBeInTheDocument()
    } finally {
      useReportStore.getState().setFilters({ groupBy: 'category' })
    }
  })
})

describe('OverviewReport metric cards', () => {
  it('shows deltas, savings rate, and runway from the dashboard data', () => {
    setQuery({
      data: {
        net_worth: '1100',
        net_worth_prev: '1000',
        net_worth_entered: 0,
        net_worth_change: 100,
        burn_rate_30: 900,
        burn_rate_prior_60: 600,
        savings_rate: 0.25,
        runway: overviewRunway(),
        income_this_month: '4000',
        expenses_this_month: '3000',
        expenses_prev_month: '2500',
        debt_payments_this_month: '500',
        outflows_this_month: '3500',
        top_categories: [{ id: 'c1', name: 'Groceries', group_name: 'Everyday', total: 300 }],
        means_months: [
          { month: '2026-01-01', income: 4000, outflows: 3000 },
          { month: '2026-02-01', income: 4000, outflows: 4100 },
        ],
      },
    })
    renderReport(<OverviewReport budgetId="b1" />)

    // 3,500 of outflows on 4,000 of income: the means card leads the row.
    // Its states and dialog are LivingMeansCard.test.tsx.
    expect(card('Your Means')).toEqual({
      value: 'Below',
      sub: '$500.00 left over · 13% under income',
    })
    expect(screen.getByRole('button', { name: /^Living below your means/ })).toBeInTheDocument()
    // Right after it, the same reading over the served months, whatever the range.
    expect(card('Means trend')).toEqual({ value: 'Keeping 12%', sub: 'over 3 months' })
    expect(
      screen.getByRole('img', { name: '1 of the last 2 months below your means' })
    ).toBeInTheDocument()

    expect(screen.getByText('$1,100.00')).toBeInTheDocument()
    // Net worth's change in dollars, like-for-like — never a percentage, which
    // read "+225.5%" for a range in which accounts were linked.
    expect(screen.getByText(/\+\$100\.00 like-for-like since the range began/)).toBeInTheDocument()
    expect(screen.getByText(/\+20\.0%/)).toBeInTheDocument() // spending delta
    // Spending up is bad news and net worth up good, whatever the sign says:
    // "Spent +21%" was drawn green.
    expect(screen.getByText(/\+20\.0%/).closest('.metric-card__delta')).toHaveClass(
      'metric-card__delta--bad'
    )
    expect(screen.getByText('25.0%')).toBeInTheDocument() // savings rate
    // How long the money lasts if income stopped, and what it read.
    expect(card('Runway')).toEqual({
      value: '20.0 months',
      sub: 'to May 27, 2028If income stopped: Essentials, checking + emergency fund, cards paid',
    })
    expect(screen.getByText('Groceries')).toBeInTheDocument()
    // The last 30 days against the 60 before them — no day in both.
    expect(card('30-Day Burn Rate')).toEqual({
      value: '$900.00',
      sub: 'Prior 60 days: $600.00/30d · +50%',
    })
  })

  it('shows no burn change when the prior 60 days had no spending', () => {
    // A young budget: everything so far is in the last 30 days. No division by
    // zero and no percentage — "+∞%" and "0%" would both be false.
    setQuery({
      data: {
        net_worth: 0,
        burn_rate_30: 450,
        burn_rate_prior_60: 0,
        income_this_month: 0,
        expenses_this_month: 450,
        expenses_prev_month: 0,
        outflows_this_month: 450,
        top_categories: [],
        means_months: [],
        runway: overviewRunway(),
      },
    })
    renderReport(<OverviewReport budgetId="b1" />)
    expect(card('30-Day Burn Rate')).toEqual({
      value: '$450.00',
      sub: 'Prior 60 days: $0.00/30d',
    })
    // The Spent card reads the same "no prior, no percentage" rule.
    const spent = screen
      .getByText('Spent', { selector: '.metric-card__label' })
      .closest('.metric-card')
    expect(spent?.querySelector('.metric-card__delta')).toBeNull()
  })

  it('keeps Runway on screen at 0, and says the money is gone', () => {
    // Days Until Zero hid itself when cash hit zero — the moment its answer
    // mattered most. Cards owing more than the money is the same moment.
    setQuery({
      data: {
        net_worth: 0,
        burn_rate_30: 900,
        burn_rate_prior_60: 900,
        income_this_month: 0,
        expenses_this_month: 900,
        expenses_prev_month: 900,
        outflows_this_month: 900,
        top_categories: [],
        means_months: [],
        runway: overviewRunway({ money_total: -300, months: 0, runs_out_on: '2026-09-26' }),
      },
    })
    renderReport(<OverviewReport budgetId="b1" />)
    expect(card('Runway')).toEqual({
      value: '0.0 months',
      sub: 'Nothing left once the cards are paidIf income stopped: Essentials, checking + emergency fund, cards paid',
    })
    const runway = screen.getByText('Runway', { selector: '.metric-card__label' })
    expect(runway.closest('.metric-card')).toHaveClass('metric-card--warning')
  })

  it('says why the runway fell back to checking and all spending', () => {
    setQuery({
      data: {
        net_worth: 0,
        burn_rate_30: 900,
        burn_rate_prior_60: 900,
        income_this_month: 0,
        expenses_this_month: 900,
        expenses_prev_month: 900,
        outflows_this_month: 900,
        top_categories: [],
        means_months: [],
        runway: overviewRunway({
          spending: 'all',
          money: 'checking',
          months: 2.5,
          runs_out_on: '2026-12-11',
          fund_chosen: false,
          essentials_known: false,
        }),
      },
    })
    renderReport(<OverviewReport budgetId="b1" />)
    expect(card('Runway')).toEqual({
      value: '2.5 months',
      sub:
        'to Dec 11, 2026If income stopped: all spending, checking, cards paid' +
        'Nothing tagged Essential, no emergency fund chosen',
    })
  })

  it('names the as-paid essentials figure under the spread one', () => {
    setQuery({
      data: {
        net_worth: '0',
        burn_rate_30: '0',
        burn_rate_prior_60: '0',
        income_this_month: '0',
        outflows_this_month: '0',
        top_categories: [],
        means_months: [],
        runway: overviewRunway(),
        essentials: {
          as_paid: 2800,
          spread: 2200,
          spread_on: true,
          monthly: 2200,
          window_start: '2026-06-01',
          window_end: '2026-08-31',
        },
      },
    })
    renderReport(<OverviewReport budgetId="b1" />)
    // The months it averages first (D6), then the other figure. The 6-month
    // target left: it is the Emergency Fund report's, and said twice it was
    // one more figure to reconcile.
    expect(card('Essentials / month')).toEqual({
      value: '$2,200.00',
      sub: 'Jun 26 – Aug 26 average$2,200.00/mo spread · $2,800.00/mo as paid',
    })
  })

  it('asks for categories tagged Essential, not payees, before there is a figure', () => {
    // Essential is a category tag only; a payee tag counts for nothing. The
    // first-run prompt still said "Tag categories or payees Essential".
    setQuery({
      data: {
        net_worth: '0',
        burn_rate_30: '0',
        burn_rate_prior_60: '0',
        income_this_month: '0',
        outflows_this_month: '0',
        top_categories: [],
        means_months: [],
        runway: overviewRunway(),
      },
    })
    renderReport(<OverviewReport budgetId="b1" />)
    expect(card('Essentials / month')).toEqual({ value: '—', sub: 'Tag categories Essential' })
    expect(card('Your Means')).toEqual({ value: '—', sub: 'No income recorded' })
  })
})

/** What /reports/savings-contributors serves, merged into each card's own
 *  payload below: every hook in this suite returns one shared state, so the
 *  dialog a card opens reads the same object the card did. The dialog's own
 *  rows and states are SavingsRateDialog.test.tsx. */
const CONTRIBUTORS = {
  income: 4000,
  savings: 1000,
  debt_principal: 500,
  savings_contributors: [
    {
      kind: 'account',
      id: 'a1',
      name: 'Cascade Point HYSA',
      reason: 'transfer_to_tracked_asset',
      reason_label: 'transfer to a tracked account',
      total: 1000,
      count: 1,
    },
  ],
  debt_contributors: [],
  income_sources: [{ payee_id: 'p1', payee_name: 'Northwind Payserv', total: 4000, count: 1 }],
}

describe('BurnRateReport', () => {
  it('compares the newest 30 days with the prior 60 on its cards', () => {
    setQuery({
      data: {
        points: [
          { date: '2026-08-01', rolling_30: 600, prior_60: 600 },
          { date: '2026-09-01', rolling_30: 900, prior_60: 600 },
        ],
      },
    })
    renderReport(<BurnRateReport budgetId="b1" />)
    expect(card('Current 30-Day Burn')).toEqual({
      value: '$900.00',
      sub: '+50% on the prior 60 days',
    })
    expect(card('Prior 60 Days')).toEqual({ value: '$600.00', sub: 'Averaged per 30 days' })
  })

  it('says there is nothing to compare when the prior 60 days are empty', () => {
    setQuery({ data: { points: [{ date: '2026-09-01', rolling_30: 450, prior_60: 0 }] } })
    renderReport(<BurnRateReport budgetId="b1" />)
    expect(card('Current 30-Day Burn').sub).toBe('No spending in the prior 60 days')
  })
})

describe('CashProjectionReport', () => {
  const projection = (goes: string | null, p10: string | null) => ({
    start_balance: 900,
    points: [
      { date: '2026-09-26', p10: 900, p25: 900, p50: 900, p75: 900, p90: 900 },
      {
        date: '2026-10-26',
        p10: -150,
        p25: 300,
        p50: 700,
        p75: 1100,
        p90: 1600,
      },
    ],
    events: [],
    goes_negative_date: goes,
    p10_negative_date: p10,
    if_income_stopped: ifIncomeStopped(),
  })

  it('says a 1 in 10 dip softly when only the low band crosses', () => {
    setQuery({ data: projection(null, '2026-10-20') })
    renderReport(<CashProjectionReport budgetId="b1" />)
    const warning = document.querySelector('.projection-warning')
    expect(warning).toHaveClass('projection-warning--possible')
    expect(warning?.textContent).toMatch(/^About a 1 in 10 chance of dipping below \$0\.00 by /)
  })

  it('says it plainly when the median crosses', () => {
    setQuery({ data: projection('2026-10-24', '2026-10-20') })
    renderReport(<CashProjectionReport budgetId="b1" />)
    const warning = document.querySelector('.projection-warning')
    expect(warning).not.toHaveClass('projection-warning--possible')
    expect(warning?.textContent).toMatch(/^More likely than not to be below \$0\.00 by /)
  })

  it('keys both bands, in the words the info panel uses', () => {
    setQuery({ data: projection(null, null) })
    renderReport(<CashProjectionReport budgetId="b1" />)
    expect(document.querySelector('.projection-warning')).toBeNull()
    const key = document.querySelector('.chart-key')?.textContent ?? ''
    expect(key).toContain('Middle half (25–75%)')
    expect(key).toContain('8 in 10 (10–90%)')
    expect(card('Projected (90d)')).toEqual({
      value: '$700.00',
      sub: '8 in 10: -$150.00 – $1,600.00',
    })
  })

  describe('if income stopped', () => {
    afterEach(() => useReportStore.setState({ runwaySpending: null, runwayMoney: null }))

    // Bands that reach the line's height (up to 10,000), so the chart draws it.
    const besideLine = () => ({
      ...projection(null, null),
      points: [
        { date: '2026-09-26', p10: 9000, p25: 9000, p50: 9000, p75: 9000, p90: 9000 },
        { date: '2026-10-26', p10: 6000, p25: 7000, p50: 8000, p75: 9000, p90: 10000 },
      ],
    })

    it('opens on the Overview’s runway and says what it read', () => {
      setQuery({ data: besideLine() })
      renderReport(<CashProjectionReport budgetId="b1" />)
      // 10,000 of checking and fund, cards paid, at 1,000 of Essentials.
      expect(card('If income stopped')).toEqual({
        value: '10.0 months',
        sub: 'to Jan 1, 2027Essentials, checking + emergency fund, cards paid',
      })
      const spending = screen.getByRole('group', { name: 'Spending' })
      expect(within(spending).getByRole('button', { name: 'Essentials' })).toHaveAttribute(
        'aria-pressed',
        'true'
      )
      const money = screen.getByRole('group', { name: 'Money' })
      expect(within(money).getByRole('button', { name: '+ Emergency fund' })).toHaveAttribute(
        'aria-pressed',
        'true'
      )
    })

    it('remembers a pick, and draws it', () => {
      setQuery({ data: besideLine() })
      renderReport(<CashProjectionReport budgetId="b1" />)
      fireEvent.click(screen.getByRole('button', { name: 'All' }))
      fireEvent.click(screen.getByRole('button', { name: '+ Savings accounts' }))
      expect(useReportStore.getState()).toMatchObject({
        runwaySpending: 'all',
        runwayMoney: 'with_savings',
      })
      expect(card('If income stopped')).toEqual({
        value: '6.3 months',
        sub: 'to Jan 1, 2027all spending, checking + savings accounts, cards paid',
      })
    })

    it('disables + Emergency fund with no fund chosen, and falls back from a remembered one', () => {
      useReportStore.setState({ runwayMoney: 'with_fund' })
      setQuery({
        data: { ...besideLine(), if_income_stopped: ifIncomeStopped({ noFund: true }) },
      })
      renderReport(<CashProjectionReport budgetId="b1" />)
      expect(screen.getByRole('button', { name: '+ Emergency fund' })).toBeDisabled()
      expect(card('If income stopped').sub).toBe('to Jan 1, 2027Essentials, checking, cards paid')
    })

    it('keys the line by its question, and the Scheduled only line is gone', () => {
      setQuery({ data: besideLine() })
      renderReport(<CashProjectionReport budgetId="b1" />)
      const key = document.querySelector('.chart-key')?.textContent ?? ''
      expect(key).toContain('If income stopped')
      expect(key).not.toContain('Scheduled only')
      fireEvent.click(screen.getByRole('button', { name: 'About the Cash Projection report' }))
      expect(screen.queryByText(/no random daily spending/)).toBeNull()
      expect(screen.getByText(/credit\s+cards owe already paid/)).toBeInTheDocument()
    })

    it('leaves a line far above the projection off the chart, and says so on its card', () => {
      // 10,000 of checking and fund against bands that reach 1,600: drawn, the
      // axis ran to 10,000 and the fan flattened into a stripe.
      setQuery({ data: projection(null, null) })
      renderReport(<CashProjectionReport budgetId="b1" />)
      const key = document.querySelector('.chart-key')?.textContent ?? ''
      expect(key).not.toContain('If income stopped')
      expect(card('If income stopped')).toEqual({
        value: '10.0 months',
        sub:
          'to Jan 1, 2027Essentials, checking + emergency fund, cards paid' +
          'Not drawn: it starts far above the projection',
      })
    })
  })
})

describe('the savings-rate cards open what contributed', () => {
  beforeEach(async () => {
    // A dialog opened in more than one test leaves a deferred history.back().
    await new Promise((r) => setTimeout(r, 0))
    await new Promise((r) => setTimeout(r, 0))
    window.history.replaceState(null, '')
  })

  const dashboard = {
    net_worth: 0,
    net_worth_prev: 0,
    burn_rate_30: 0,
    burn_rate_prior_60: 0,
    essentials_tagged: false,
    savings_rate: 0.25,
    income_this_month: 4000,
    expenses_this_month: 2500,
    expenses_prev_month: 0,
    debt_payments_this_month: 500,
    outflows_this_month: 3000,
    top_categories: [],
    means_months: [],
    runway: overviewRunway(),
  }

  it('the Overview card asks for the range the Overview shows', () => {
    useReportStore.getState().setFilters({ startDate: '2026-03-01', endDate: '2026-03-31' })
    setQuery({ data: { ...dashboard, ...CONTRIBUTORS } })
    renderReport(<OverviewReport budgetId="b1" />)

    // Lazy: nothing is fetched until the card is opened.
    expect(hookCalls.get('useSavingsContributors')).toBeUndefined()
    fireEvent.click(
      screen.getByRole('button', { name: 'Savings rate 25.0%. Show what contributed' })
    )

    const dialog = screen.getByRole('dialog', { name: 'Savings rate' })
    expect(hookCalls.get('useSavingsContributors')?.at(-1)).toEqual([
      'b1',
      '2026-03-01',
      '2026-03-31',
    ])
    expect(within(dialog).getByText('25.0%')).toBeInTheDocument()
    expect(within(dialog).getByText('Saved ÷ Income')).toBeInTheDocument()
    expect(dialog).toHaveTextContent('Cascade Point HYSA')
    useReportStore.getState().resetFilters()
  })

  const tab = {
    months: [],
    start_date: '2026-01-01',
    end_date: '2026-03-15',
    summary: {
      income: 4000,
      spending: 2500,
      savings: 1000,
      debt_principal: 500,
      savings_rate: 0.25,
      savings_rate_with_debt: 0.375,
    },
  }

  it('the tab card asks for the window its summary covers, as served', () => {
    setQuery({ data: { ...tab, ...CONTRIBUTORS } })
    renderReport(<SavingsRateReport budgetId="b1" />)

    fireEvent.click(
      screen.getByRole('button', { name: 'Savings rate 25.0%. Show what contributed' })
    )

    const dialog = screen.getByRole('dialog', { name: 'Savings rate' })
    expect(hookCalls.get('useSavingsContributors')?.at(-1)).toEqual([
      'b1',
      '2026-01-01',
      '2026-03-15',
    ])
    expect(within(dialog).getByText('25.0%')).toBeInTheDocument()
    expect(within(dialog).getByText('Saved ÷ Income')).toBeInTheDocument()
    expect(dialog).toHaveTextContent('Not part of this rate.')
  })

  it('the tab opens without debt payments, as the Overview does', () => {
    // The tab defaulted to counting them while the Overview did not, so one
    // month read 4.9% here and 0.0% there.
    setQuery({ data: { ...tab, ...CONTRIBUTORS } })
    renderReport(<SavingsRateReport budgetId="b1" />)
    expect(screen.getByRole('button', { name: 'Include debt payments' })).toHaveAttribute(
      'aria-pressed',
      'false'
    )
    expect(card('Savings rate').value).toBe('25.0%')
    expect(card('Saved').value).toBe('$1,000.00')
    expect(card('Debt payments').sub).toBe('not in this rate')
  })

  it('with debt payments on, every label says so and Saved adds them', () => {
    setQuery({ data: { ...tab, ...CONTRIBUTORS } })
    renderReport(<SavingsRateReport budgetId="b1" />)
    fireEvent.click(screen.getByRole('button', { name: 'Include debt payments' }))

    expect(card('Savings rate with debt payments').value).toBe('37.5%')
    // The card read "Saved $1,000" beside a rate that also counted $500 of
    // debt payments, so its figures did not divide into its rate.
    expect(card('Saved + debt payments').value).toBe('$1,500.00')
    expect(card('Debt payments').sub).toBe('in this rate')
    expect(screen.queryByText('Debt Paid Down')).toBeNull()

    fireEvent.click(
      screen.getByRole('button', {
        name: 'Savings rate with debt payments 37.5%. Show what contributed',
      })
    )
    const dialog = screen.getByRole('dialog', { name: 'Savings rate with debt payments' })
    expect(within(dialog).getByText('37.5%')).toBeInTheDocument()
    expect(within(dialog).getByText('(Saved + Debt payments) ÷ Income')).toBeInTheDocument()
  })

  it('both cards print a negative rate the same way', () => {
    // The Overview clamped to 0.0% with its own formatter; the tab printed it.
    setQuery({ data: { ...dashboard, savings_rate: -0.03 } })
    const { unmount } = renderReport(<OverviewReport budgetId="b1" />)
    expect(card('Savings rate').value).toBe('-3.0%')
    unmount()

    setQuery({ data: { ...tab, summary: { ...tab.summary, savings_rate: -0.03 } } })
    renderReport(<SavingsRateReport budgetId="b1" />)
    expect(card('Savings rate').value).toBe('-3.0%')
  })
})

describe('SubscriptionsReport table', () => {
  function service(overrides: Record<string, unknown> = {}) {
    return {
      payee_id: 'p1',
      payee_name: 'Quarterly Gym',
      basis: 'observed',
      annual: 120,
      monthly: 10,
      interval_days: 91,
      cadence: 'days',
      cadence_assumed: false,
      latest_charge: 30,
      first_charge_date: '2024-02-01',
      last_charge_date: '2026-08-01',
      charges_in_year: 4,
      refunded_in_year: 0,
      ...overrides,
    }
  }

  function report(services: ReturnType<typeof service>[]) {
    return {
      subscriptions: [
        {
          category_id: 'c1',
          category_name: 'Fitness',
          group_name: 'Wellbeing',
          annual: 120,
          monthly: 10,
          monthly_amounts: [30, 0, 0, 30],
          total: 60,
          last_charge_date: '2026-08-01',
          services,
        },
      ],
      summary: {
        total_annual: 120,
        total_monthly: 10,
        charged_categories: 1,
        tagged_categories: 3,
        new_this_month: 0,
        projected_services: 0,
        stopped_services: 0,
      },
      months: ['2026-05-01', '2026-06-01', '2026-07-01', '2026-08-01'],
      monthly_totals: [30, 0, 0, 30],
      year_start: '2025-09-01',
      year_end: '2026-08-31',
    }
  }

  it('reads Monthly as Annual ÷ 12 and Active as N of M', () => {
    setQuery({ data: report([service()]) })
    renderReport(<SubscriptionsReport budgetId="b1" />)

    expect(card('Monthly')).toEqual({ value: '$10.00', sub: 'Annual ÷ 12' })
    expect(card('Annual')).toEqual({ value: '$120.00', sub: 'last 12 complete months' })
    expect(card('Active')).toEqual({ value: '1 of 3', sub: 'tagged categories charged' })
  })

  it('leads with the tagged category and opens onto its services', () => {
    // The tag is on categories, so the category is the line. Listing payees
    // at the top level made the tag a filter and left the envelope unnamed.
    setQuery({ data: report([service()]) })
    renderReport(<SubscriptionsReport budgetId="b1" />)

    expect(screen.getByText('Category')).toBeInTheDocument()
    const row = screen.getByRole('button', { name: /Fitness/, expanded: false })
    expect(row).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('Quarterly Gym')).toBeNull()

    fireEvent.click(row)

    expect(row).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('Quarterly Gym')).toBeInTheDocument()
    expect(screen.getByText('every 91 days')).toBeInTheDocument()
    // $30 a charge, $10 a month: both visible.
    expect(screen.getByText('$30.00')).toBeInTheDocument()
  })

  it('opens a service onto its own charges', () => {
    setQuery({ data: report([service()]) })
    renderReport(<SubscriptionsReport budgetId="b1" />)
    fireEvent.click(screen.getByRole('button', { name: /Fitness/, expanded: false }))

    fireEvent.click(screen.getByRole('button', { name: 'List charges from Quarterly Gym' }))

    expect(useReportStore.getState().drillDown).toMatchObject({
      kind: 'payee',
      categoryIds: ['c1'],
      payeeIds: ['p1'],
      startDate: '2025-09-01',
    })
  })

  it('marks a stopped service and a projected one', () => {
    setQuery({
      data: report([
        service({ payee_id: 'p2', payee_name: 'Fresh Plan', basis: 'new' }),
        service({ payee_id: 'p3', payee_name: 'Old Plan', basis: 'stopped', annual: 0 }),
      ]),
    })
    renderReport(<SubscriptionsReport budgetId="b1" />)
    fireEvent.click(screen.getByRole('button', { name: /Fitness/, expanded: false }))

    expect(screen.getByText('new · projected')).toBeInTheDocument()
    expect(screen.getByText('stopped')).toBeInTheDocument()
  })
})

describe('VolatilityReport amortize toggle', () => {
  it('asks for the amortized reading once the box is ticked', () => {
    // Without the flag reaching the hook, the chart kept showing the raw
    // reading while its info panel described the amortized one.
    setQuery({ data: { categories: [], amortized: false, window_start: '', window_end: '' } })
    renderReport(<VolatilityReport budgetId="b1" />)
    const months = useReportStore.getState().rangeMonths
    expect(hookCalls.get('useVolatilityReport')?.at(-1)).toEqual(['b1', months, false])

    fireEvent.click(screen.getByRole('checkbox', { name: 'Amortize lumpy charges' }))

    expect(hookCalls.get('useVolatilityReport')?.at(-1)).toEqual(['b1', months, true])
  })
})

describe('VolatilityReport drill-down', () => {
  it('opens the window the statistics read, as served', () => {
    // The chart computed its own window — `monthsAgoStartISO(months - 1)`
    // through today — under a comment calling it the backend's. The backend
    // reads complete months, so the panel added the partial current month and
    // dropped the oldest one, and its total could not reconcile.
    setQuery({
      data: {
        categories: [
          {
            category_id: 'c1',
            category_name: 'Groceries',
            category_group_name: 'Everyday',
            mean: 400,
            std_dev: 20,
            min_val: 380,
            max_val: 420,
            p25: 390,
            p75: 410,
            months_included: 6,
          },
        ],
        amortized: false,
        window_start: '2026-03-01',
        window_end: '2026-08-31',
      },
    })
    renderReport(<VolatilityReport budgetId="b1" />)

    fireEvent.click(screen.getByRole('cell', { name: 'Groceries' }))

    const drill = useReportStore.getState().drillDown
    expect(drill).toMatchObject({ startDate: '2026-03-01', endDate: '2026-08-31' })
  })
})

describe('DayPatternsReport', () => {
  // Both hooks share this mock's data, so each row carries the day-of-week
  // fields and the payday fields.
  const both = {
    days: [0, 1].map((i) => ({
      day_of_week: i,
      day_name: i ? 'Tuesday' : 'Monday',
      total: i ? 300 : 100,
      count: 2,
      weekdays: 5,
      avg_per_day: i ? 60 : 20,
      offset: i,
      median_spend: i ? 45 : 5,
      paydays: 26,
    })),
    counted_classes: ['spending'],
    window_start: '2026-01-01',
    window_end: '2026-09-25',
    baseline_daily: 12,
    baseline_days: 268,
    event_count: 26,
    payday_floor: 200,
  }

  it('ranks the weekdays by a typical day, not by their totals', () => {
    setQuery({ data: both })
    renderReport(<DayPatternsReport budgetId="b1" />)
    // "Average", not "typical": typical means the median everywhere else.
    expect(card('Busiest day')).toEqual({ value: 'Tuesday', sub: '$60.00 on an average Tuesday' })
    expect(card('Quietest day')).toEqual({ value: 'Monday', sub: '$20.00 on an average Monday' })
    // It says which date it reads: a Saturday shop can post on Monday.
    expect(screen.getByText(/by the bank.s posting date/)).toBeInTheDocument()
  })

  it('states the typical day as a median over the days it read', () => {
    // The baseline averaged only the days outside every payday window, so
    // biweekly pay at 14 days had none, and the card read "no baseline".
    setQuery({ data: both })
    renderReport(<DayPatternsReport budgetId="b1" />)
    expect(card('Typical day')).toEqual({ value: '$12.00', sub: 'Median of 268 days' })
    expect(card('Peak day after payday')).toEqual({
      value: 'Day +1',
      sub: '$45.00 on the median payday',
    })
    expect(screen.getByText(/26 paydays/)).toBeInTheDocument()
  })

  it('states the payday rule the server applied, and that it counts spending only', () => {
    // The panel said scheduled bills were excluded (they never were) and said
    // nothing of the floor that decides what a payday is, nor of the class
    // rule the Day-of-Week panel above it explains. The floor is served, so
    // the copy cannot drift from it: 250 here, not the backend's default.
    setQuery({
      data: {
        days: [],
        counted_classes: ['spending'],
        window_start: '2026-01-01',
        window_end: '2026-09-25',
        baseline_daily: 12,
        baseline_days: 268,
        event_count: 3,
        payday_floor: 250,
      },
    })
    renderReport(<DayPatternsReport budgetId="b1" />)
    fireEvent.click(screen.getByRole('button', { name: 'About the Payday Effect report' }))

    const panel = within(screen.getByRole('dialog', { name: 'Payday Effect' }))
    expect(panel.getByText(/is an income deposit/).textContent).toContain(
      '$250.00 or more into a cash account'
    )
    expect(panel.queryByText(/scheduled bills/)).toBeNull()
    // Discretionary only: a bill due two days after pay is not a splurge.
    expect(panel.getByText(/Discretionary only/)).toBeInTheDocument()
  })
})

describe('WishlistDisciplineReport', () => {
  const report = {
    cooled_then_bought: 0,
    cooled_then_dropped: 0,
    bought_early: 0,
    dropped_early: 0,
    still_open: 0,
    ready_to_decide: 0,
    still_cooling: 0,
    decided_count: 0,
    waited_out_count: 0,
    waited_out_share: null,
    resisted_total: 0,
    resisted_count: 0,
    bought_total: 0,
    bought_count: 0,
    open_total: 0,
    avg_days_to_buy: null,
    avg_wish_cost: 100,
    unplaced: 0,
    cooling_days: 30,
  }

  it('does not credit the wait with a wish dropped before it was up', () => {
    // One $600 wish dropped on day ten of thirty. The report led with
    // "Resisted $600" as if the wait had done it.
    setQuery({
      data: {
        ...report,
        dropped_early: 1,
        decided_count: 1,
        waited_out_share: 0,
        resisted_total: 600,
        resisted_count: 1,
      },
    })
    renderReport(<WishlistDisciplineReport budgetId="b1" />)

    expect(card('Waited it out')).toEqual({ value: '0%', sub: '0 of 1 wish decided' })
    // "1 talked yourself out of" is gone, and the two money cards say the
    // same two things in the same words.
    expect(card('Resisted').sub).toBe('1 wish · 0 after the wait')
    expect(screen.queryByText(/talked yourself out of/)).toBeNull()
    const row = screen.getByText('Decided against before the wait was up').closest('tr')
    expect(row).toHaveTextContent('1')
  })

  it('leads with the share of decided wishes that waited it out', () => {
    setQuery({
      data: {
        ...report,
        cooled_then_bought: 2,
        cooled_then_dropped: 1,
        bought_early: 1,
        decided_count: 4,
        waited_out_count: 3,
        waited_out_share: 0.75,
        resisted_total: 200,
        resisted_count: 1,
        bought_total: 900,
        bought_count: 3,
        avg_days_to_buy: 24,
      },
    })
    renderReport(<WishlistDisciplineReport budgetId="b1" />)

    const labels = Array.from(document.querySelectorAll('.metric-card__label')).map(
      (l) => l.textContent
    )
    expect(labels[0]).toBe('Waited it out')
    expect(card('Waited it out')).toEqual({ value: '75%', sub: '3 of 4 wishes decided' })
    expect(card('Bought').sub).toBe('3 wishes · 2 after the wait')
    // A mean, beside the person's own waiting period — not "Typical".
    expect(card('Average wait')).toEqual({ value: '24d', sub: 'to buy · your wait is 30 days' })
    expect(screen.queryByText('Typical wait')).toBeNull()
  })

  it('says how many open wishes are past their wait', () => {
    setQuery({
      data: { ...report, still_open: 3, ready_to_decide: 2, still_cooling: 1, open_total: 450 },
    })
    renderReport(<WishlistDisciplineReport budgetId="b1" />)

    expect(card('Waiting').sub).toBe('3 wishes · 2 ready to decide')
    expect(screen.getByText('Wait over, ready to decide').closest('tr')).toHaveTextContent('2')
    expect(screen.getByText('Still in the wait').closest('tr')).toHaveTextContent('1')
    expect(card('Waited it out')).toEqual({ value: '—', sub: 'nothing decided yet' })
  })
})

describe('PayeeReport labels', () => {
  const payees = Array.from({ length: 25 }, (_, i) => ({
    payee_id: `p${i}`,
    payee_name: `Payee ${i}`,
    total: 100 - i,
    count: 1,
    pct: 1,
    monthly_trend: [],
    top_categories: [],
    is_recurring: false,
  }))

  it('says how many the view shows, not how many the server ranked', () => {
    // The card read "top 25 shown" while the Top view drew and listed 20.
    setQuery({ data: { payees, total: 9850, payee_count: 312, payees_to_80pct: 140 } })
    renderReport(<PayeeReport budgetId="b1" />)

    expect(screen.getByText('20 shown')).toBeInTheDocument()
    expect(screen.queryByText('top 25 shown')).toBeNull()
    expect(screen.getByText('all payees')).toBeInTheDocument()
  })

  it('counts every payee and totals every payee, beside the rows it shows', () => {
    // Total Payees read `payees.length` (the ranking cap) and Total Spent the
    // ranked rows summed, so a 312-payee budget was told it had 25.
    setQuery({
      data: { payees: payees.slice(0, 2), total: 1050, payee_count: 5, payees_to_80pct: 3 },
    })
    renderReport(<PayeeReport budgetId="b1" />)

    expect(card('Total Payees')).toEqual({ value: '5', sub: '2 shown' })
    expect(card('Recurring Payees').sub).toBe('of the top 2')
    expect(card('Total Spent').value).toBe('$1,050.00')
    // The table's wider row carries the share, because Payee's % column is a
    // share of that same served total: 199 of 1,050.
    expect(cellsOf('of $1,050.00 across 5 payees')).toContain('19.0%')
  })

  it('does not call a payee-filtered total "all payees"', () => {
    useReportStore.getState().setFilters({ payeeIds: ['p1', 'p2', 'p3'] })
    try {
      setQuery({
        data: { payees: payees.slice(0, 3), total: 250, payee_count: 3, payees_to_80pct: 3 },
      })
      renderReport(<PayeeReport budgetId="b1" />)
      expect(screen.getByText('selected payees')).toBeInTheDocument()
      expect(screen.queryByText('all payees')).toBeNull()
    } finally {
      useReportStore.getState().setFilters({ payeeIds: [] })
    }
  })
})

describe('IncomeSourcesReport average', () => {
  it('shows the served average, not total over the months listed', () => {
    // The page divided `total` by `months.length` for itself, with the running
    // month in the window: 5,500 beside Cost of Living's Take-home of 6,000
    // for the same steady pay. The server serves the figure both quote.
    setQuery({
      data: {
        months: ['2026-06-01', '2026-07-01', '2026-08-01'],
        sources: [
          {
            payee_id: 'p1',
            payee_name: 'Northwind Payserv',
            monthly: [6000, 6000, 6000],
            total: 18000,
            count: 3,
          },
        ],
        monthly_totals: [6000, 6000, 6000],
        total: 18000,
        // Deliberately not total ÷ months, so a division done here would show.
        avg_monthly: 5750,
        months_averaged: 3,
      },
    })
    renderReport(<IncomeSourcesReport budgetId="b1" />)
    expect(screen.getByText('$5,750.00')).toBeInTheDocument()
  })
})

describe('IncomeExpenseReport drill', () => {
  it('opens a month’s Expenses with its refunds, so the list totals the row', () => {
    setQuery({
      data: {
        months: [
          {
            month: '2026-08-01',
            partial_month: false,
            income: 6000,
            expenses: 1530,
            savings: 0,
            debt_principal: 0,
            net: 4470,
          },
        ],
        // The classes are served; the client's copy of them is gone.
        expense_classes: ['spending'],
      },
    })
    renderReport(<IncomeExpenseReport budgetId="b1" />)
    fireEvent.click(
      screen.getByRole('button', { name: 'Expenses, Aug 26: $1,530.00. Show the rows' })
    )
    const drill = useReportStore.getState().drillDown
    expect(drill).toMatchObject({
      label: 'Expenses · Aug 26',
      scope: 'leaf',
      activityClasses: ['spending'],
      startDate: '2026-08-01',
      endDate: '2026-08-31',
    })
    expect(drill?.direction).toBeUndefined()
    useReportStore.getState().setDrillDown(null)
  })
})

describe('IncomeExpenseReport table', () => {
  const months = [
    {
      month: '2026-07-01',
      partial_month: false,
      income: 5000,
      expenses: 3000,
      savings: 500,
      savings_moved: 500,
      savings_held: 0,
      debt_principal: 400,
      net: 1100,
    },
    {
      month: '2026-08-01',
      partial_month: false,
      income: 5000,
      expenses: 4800,
      savings: -1000,
      savings_moved: -1000,
      savings_held: 0,
      debt_principal: 400,
      net: 800,
    },
    {
      month: '2026-09-01',
      partial_month: true,
      income: 2500,
      expenses: 1900,
      savings: 0,
      savings_moved: 0,
      savings_held: 0,
      debt_principal: 0,
      net: 600,
    },
  ]

  it('lists Income, Expenses, Saved, Debt payments and Net, with the window total', () => {
    setQuery({ data: { months, expense_classes: ['spending'] } })
    renderReport(<IncomeExpenseReport budgetId="b1" />)
    const headers = within(screen.getByRole('table'))
      .getAllByRole('columnheader')
      .map((h) => h.textContent)
    expect(headers).toEqual(['Month', 'Income', 'Expenses', 'Saved', 'Debt payments', 'Net'])
    // Saved is Saved alone — the bar used to add debt payments under the
    // same name the ⓘ defined without them.
    expect(cellsOf('Jul 26')).toEqual([
      'Jul 26',
      '$5,000.00',
      '$3,000.00',
      '$500.00',
      '$400.00',
      '$1,100.00',
    ])
    // The complete months only: September is a row, "so far", not a term.
    // The label is the row's header cell; these are its figures.
    expect(cellsOf('Total · Jul 26 – Aug 26')).toEqual([
      '$10,000.00',
      '$7,800.00',
      '-$500.00',
      '$800.00',
      '$1,900.00',
    ])
    expect(screen.getByText('Sep 26 so far')).toBeInTheDocument()
  })

  it('drops the Debt payments column when there were none', () => {
    setQuery({
      data: {
        months: months.map((m) => ({ ...m, debt_principal: 0 })),
        expense_classes: ['spending'],
      },
    })
    renderReport(<IncomeExpenseReport budgetId="b1" />)
    expect(screen.queryByRole('columnheader', { name: 'Debt payments' })).toBeNull()
  })

  it('opens a month’s Income from its cell', () => {
    setQuery({ data: { months, expense_classes: ['spending'] } })
    renderReport(<IncomeExpenseReport budgetId="b1" />)
    fireEvent.click(
      screen.getByRole('button', { name: 'Income, Jul 26: $5,000.00. Show the rows' })
    )
    expect(useReportStore.getState().drillDown).toMatchObject({
      label: 'Income · Jul 26',
      startDate: '2026-07-01',
      endDate: '2026-07-31',
    })
    useReportStore.getState().setDrillDown(null)
  })
})

describe('TimelineReport amounts', () => {
  it('keeps the sign, and names money back into a spending envelope', () => {
    setQuery({
      data: {
        transactions: [
          {
            id: 't1',
            date: '2026-08-14',
            amount: 5000,
            payee_name: 'Harborstone Roofing',
            category_name: 'Home Repair',
            memo: null,
            activity_class: 'spending',
            activity_label: 'Spending',
          },
          {
            id: 't2',
            date: '2026-08-10',
            amount: -250,
            payee_name: 'Corner Market',
            category_name: 'Groceries',
            memo: null,
            activity_class: 'spending',
            activity_label: 'Spending',
          },
        ],
        class_excluded: [],
        filter_unavailable: false,
      },
    })
    renderReport(<TimelineReport budgetId="b1" />)
    const refund = screen.getByText('Harborstone Roofing').closest('.timeline__card')!
    expect(refund.querySelector('.timeline__amount')?.textContent).toBe('$5,000.00Refund')
    const purchase = screen.getByText('Corner Market').closest('.timeline__card')!
    expect(purchase.querySelector('.timeline__amount')?.textContent).toBe('-$250.00')
  })
})

describe('SpendingTrendsReport legend', () => {
  it('lists the stack in order, Other last, in its own key rather than recharts’', () => {
    // Twelve categories: ten named, two in Other. recharts' <Legend> sorted
    // them by name, and with eight palette slots two pairs shared a colour
    // with nothing on the page to tell them apart.
    const series = Array.from({ length: 12 }, (_, i) => ({
      id: `c${i}`,
      name: `Envelope ${String.fromCharCode(76 - i)}`,
      group_id: 'g',
      group_name: 'Everyday',
      monthly: [120 - i],
      total: 120 - i,
    }))
    setQuery({
      data: {
        months: ['2026-08-01'],
        series,
        monthly_totals: [series.reduce((sum, s) => sum + s.total, 0)],
        total: series.reduce((sum, s) => sum + s.total, 0),
        class_excluded: [],
        filter_unavailable: false,
      },
    })
    useReportStore.getState().setFilters({ groupBy: 'category' })
    renderReport(<SpendingTrendsReport budgetId="b1" />)
    const legend = screen.getByRole('list', { name: 'Series in this chart' })
    const names = within(legend)
      .getAllByRole('button')
      .map((b) => b.querySelector('.chart-legend__name')?.textContent)
    expect(names).toEqual([...series.slice(0, 10).map((s) => s.name), 'Other'])
    // Other holds the two it folded, the 11th and 12th: 110 and 109.
    expect(within(legend).getByRole('button', { name: 'Other, $219.00' })).toBeInTheDocument()
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
            usual_low: '80',
            usual_high: '120',
            z_score: 10,
            direction: 'high',
            partial_month: false,
            history: ['0', '0', '0', '0', '0', '100', '100', '100', '100', '100', '100', '300'],
          },
        ],
      },
    })
    renderReport(<AnomaliesReport budgetId="b1" />)

    expect(screen.getByText('Dining')).toBeInTheDocument()
    expect(screen.getByText('+200%')).toBeInTheDocument()
  })

  it('drills a current-month anomaly through today, not to the month end', () => {
    // The drill once built its own month-end window: for the current month it
    // asked for days that had not happened, so the panel could total more
    // than the card that opened it.
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 8, 10, 12, 0))
    try {
      setQuery({
        data: {
          anomalies: [
            {
              category_id: 'c1',
              category_name: 'Dining',
              group_name: 'Everyday',
              month: '2026-09-01',
              actual: '300',
              baseline_mean: '100',
              usual_low: '80',
              usual_high: '120',
              z_score: 10,
              direction: 'high',
              partial_month: true,
              history: ['100', '100', '100', '300'],
            },
          ],
        },
      })
      renderReport(<AnomaliesReport budgetId="b1" />)

      fireEvent.click(screen.getByRole('button', { name: /Dining/ }))

      const drill = useReportStore.getState().drillDown
      expect(drill).toMatchObject({
        categoryIds: ['c1'],
        planSpent: true,
        startDate: '2026-09-01',
        endDate: '2026-09-10',
      })
      // The figure nets refunds; an outflow-only list totalled more than it.
      expect(drill?.direction).toBeUndefined()
    } finally {
      vi.useRealTimers()
    }
  })

  it('says a month still in progress is not finished, and a complete one is', () => {
    // The month in progress is scored against the complete months and only
    // ever flagged HIGH (backend report_stats.anomaly_scan). Its figure is
    // month-to-date, so the heading has to say so — unlabelled, a 1,200
    // grocery month reads as a closed month's total.
    const row = {
      category_id: 'c1',
      category_name: 'Groceries',
      group_name: 'Everyday',
      actual: '1200',
      baseline_mean: '400',
      usual_low: '380',
      usual_high: '420',
      z_score: 40,
      direction: 'high',
      history: ['400', '400', '1200'],
    }
    setQuery({
      data: {
        anomalies: [
          { ...row, month: '2026-09-01', partial_month: true },
          { ...row, category_id: 'c2', month: '2026-08-01', partial_month: false },
        ],
      },
    })
    renderReport(<AnomaliesReport budgetId="b1" />)

    const labels = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent)
    expect(labels).toEqual([
      expect.stringContaining('so far'),
      expect.not.stringContaining('so far'),
    ])
  })
})

describe('ParetoReport insight', () => {
  it('computes the 80% concentration from the spending groups', () => {
    setQuery({
      data: {
        groups: [
          {
            id: 'c1',
            name: 'Rent',
            total: 500,
            count: 1,
            pct: 50,
            parent_id: 'g1',
            parent_name: 'Home',
          },
          {
            id: 'c2',
            name: 'Groceries',
            total: 300,
            count: 5,
            pct: 30,
            parent_id: 'g2',
            parent_name: 'Everyday',
          },
          {
            id: 'c3',
            name: 'Gas',
            total: 150,
            count: 3,
            pct: 15,
            parent_id: 'g2',
            parent_name: 'Everyday',
          },
          {
            id: 'c4',
            name: 'Fun',
            total: 50,
            count: 2,
            pct: 5,
            parent_id: 'g2',
            parent_name: 'Everyday',
          },
        ],
        total: 1000,
      },
    })
    renderReport(<ParetoReport budgetId="b1" />)

    // total spending card (the drill table's total row shows it too)
    expect(screen.getAllByText('$1,000.00').length).toBeGreaterThan(0)
    // Rent + Groceries reach 80%: 2 of 4 categories. The card states that and
    // no more — it used to add a "spread thin, consider consolidating"
    // verdict in warning colour, advice drawn from a budget's shape.
    expect(screen.getByText('2 categories')).toBeInTheDocument()
    expect(card('80% of Spend').sub).toBe('50% of all categories')
    expect(screen.queryByText(/spread thin|concentrated/)).toBeNull()
  })

  it('draws the payee card from the served count when the top 25 hold under 80%', () => {
    // 312 payees, the 25 sent holding $4,120 of $9,850. The card looked for
    // 80% in those 25 and, finding nothing, disappeared.
    useReportStore.getState().setFilters({ groupBy: 'payee' })
    try {
      setQuery({
        data: {
          groups: [],
          payees: Array.from({ length: 25 }, (_, i) => ({
            payee_id: `p${i}`,
            payee_name: `Payee ${i}`,
            total: 4120 / 25,
          })),
          total: 9850,
          payee_count: 312,
          payees_to_80pct: 140,
        },
      })
      renderReport(<ParetoReport budgetId="b1" />)
      expect(screen.getByText('80% of Spend')).toBeInTheDocument()
      expect(screen.getByText('140 payees')).toBeInTheDocument()
    } finally {
      useReportStore.getState().setFilters({ groupBy: 'category' })
    }
  })
})

describe('SeasonalityReport in privacy mode', () => {
  afterEach(() => {
    useAppStore.setState({ privacyMode: false })
  })

  it('masks the cell labels it draws for itself', () => {
    // The heatmap's cells bypass useFormatters. With its privacy argument
    // dropped they read "4.2k" beside a legend reading "$••••", and no test
    // rendered the grid with privacy on to notice.
    useAppStore.setState({ privacyMode: true })
    setQuery({
      data: {
        months: ['2026-07-01'],
        categories: [{ id: 'c1', name: 'Electric' }],
        cells: [{ category_id: 'c1', month: '2026-07-01', total: '4180' }],
      },
    })
    const { container } = renderReport(<SeasonalityReport budgetId="b1" />)

    const value = container.querySelector('.heatmap__cell-value')
    expect(value?.textContent).toBe(PRIVACY_MASK)
    expect(container.querySelector('.heatmap__table')?.textContent).not.toMatch(/4\.2k|4180/)
  })
})

describe('CostOfLivingReport tiers', () => {
  // Two complete months, as the server now serves them: every month in the
  // window has finished, so each average is its total over both. Required
  // (75) and the essentials ratio (58.33) sit in different bands, so reading
  // the standing off the wrong one changes the note.
  const tiered = {
    months: ['2026-07-01', '2026-08-01'],
    months_averaged: 2,
    window_start: '2026-07-01',
    window_end: '2026-08-31',
    groups: [
      {
        group_id: 'g-bills',
        group_name: 'Bills',
        monthly_amounts: [700, 700],
        total: 1400,
        avg_monthly: 700,
        share: 77.78,
        category_ids: ['c1'],
      },
      {
        group_id: 'g-fun',
        group_name: 'Fun',
        monthly_amounts: [200, 200],
        total: 400,
        avg_monthly: 200,
        share: 22.22,
        category_ids: ['c2'],
      },
    ],
    // The page composes the gap (900 - 700) and both ratios (900/1200 and
    // 700/1200) from these three: `necessityView`, not the server.
    avg_monthly_cost_of_living: 900,
    avg_monthly_essentials: 700,
    avg_monthly_income: 1200,
    avg_monthly_discretionary: 180,
    basis: 'tag' as const,
    tagged: true,
    class_excluded: [],
    counted_classes: ['spending', 'debt_principal'],
  }

  it('puts each tier on its own card', () => {
    // Read inside each card: the group table and legend print Bills $700 and
    // Fun $200 too, so a page-wide search passed with the Essentials and
    // Non-essential cards swapped.
    setQuery({ data: tiered })
    renderReport(<CostOfLivingReport budgetId="b1" />)

    expect(card('Cost of living')).toEqual({
      value: '$900.00',
      sub: 'per month, over 2 complete months',
    })
    // Its window is this report's, not the Essentials headline's three
    // months, so the card says which.
    expect(card('Essentials')).toEqual({
      value: '$700.00',
      sub: 'could not be cut · per month, over 2 complete months',
    })
    expect(card('Committed, not essential').value).toBe('$200.00')
    expect(card('Take-home')).toEqual({
      value: '$1,200.00',
      sub: 'per month, over 2 complete months',
    })
    expect(card('Required')).toEqual({ value: '75%', sub: 'of take-home' })
  })

  it('opens the Uncategorized bucket by its served null id, by "no category"', () => {
    const bucket = {
      group_id: null,
      group_name: 'Uncategorized',
      monthly_amounts: [50, 50],
      total: 100,
      avg_monthly: 50,
      share: 5,
      category_ids: [],
    }
    setQuery({ data: { ...tiered, groups: [...tiered.groups, bucket] } })
    renderReport(<CostOfLivingReport budgetId="b1" />)
    fireEvent.click(
      screen.getByRole('button', { name: 'Show the transactions behind Uncategorized' })
    )
    const drill = useReportStore.getState().drillDown
    expect(drill).toMatchObject({ noCategory: true, label: 'Uncategorized' })
    expect(drill?.categoryIds).toBeUndefined()
    useReportStore.getState().setDrillDown(null)
  })

  it('opens a real group named "Uncategorized" by its categories', () => {
    // The page compared the name to the string "Uncategorized", so a group a
    // household had named that opened every row with no category instead.
    const named = {
      group_id: 'g-named',
      group_name: 'Uncategorized',
      monthly_amounts: [50, 50],
      total: 100,
      avg_monthly: 50,
      share: 5,
      category_ids: ['c9'],
    }
    setQuery({ data: { ...tiered, groups: [...tiered.groups, named] } })
    renderReport(<CostOfLivingReport budgetId="b1" />)
    fireEvent.click(
      screen.getByRole('button', { name: 'Show the transactions behind Uncategorized' })
    )
    const drill = useReportStore.getState().drillDown
    expect(drill).toMatchObject({ categoryIds: ['c9'] })
    expect(drill?.noCategory).toBeUndefined()
    useReportStore.getState().setDrillDown(null)
  })

  it('names its table for the tier it rolls up', () => {
    // The table is the WIDE tier — subscriptions and debt payments included —
    // and a screen reader announced it as "Essential spending".
    setQuery({ data: tiered })
    renderReport(<CostOfLivingReport budgetId="b1" />)
    expect(screen.getByRole('table', { name: 'Cost of living by category group' })).toBeTruthy()
  })

  it('states the gap as a share of what is committed, not as advice', () => {
    setQuery({ data: tiered })
    renderReport(<CostOfLivingReport budgetId="b1" />)

    // 200 of 900. And the card must not tell anyone to cancel anything.
    expect(card('Committed, not essential').sub).toBe('22% of cost of living')
    expect(screen.queryByText(/could cut/i)).toBeNull()
  })

  it('lays take-home out whole under the verdict', () => {
    // 900 committed + 180 discretionary of 1,200: 120 left over.
    setQuery({ data: tiered })
    renderReport(<CostOfLivingReport budgetId="b1" />)
    expect(
      screen.getByText(
        'Of $1,200.00 take-home a month: $900.00 committed (75%) · $180.00 discretionary (15%) · $120.00 left over (10%)'
      )
    ).toBeInTheDocument()
  })

  it('shows one card when everything committed is essential', () => {
    setQuery({ data: { ...tiered, avg_monthly_essentials: 900 } })
    renderReport(<CostOfLivingReport budgetId="b1" />)
    expect(card('Cost of living').sub).toBe(
      'per month, over 2 complete months · all of it Essential'
    )
    expect(screen.queryByText('Committed, not essential')).toBeNull()
    expect(screen.queryByText('Essentials')).toBeNull()
  })

  it('reads the standing off the wide ratio', () => {
    // Required 75 is "tight"; the essentials ratio, 58.33, would read
    // "workable". Swapping the arguments must change the sentence.
    setQuery({ data: tiered })
    renderReport(<CostOfLivingReport budgetId="b1" />)
    expect(screen.getByText(/Most of your take-home is committed/)).toBeInTheDocument()
    expect(screen.queryByText(/over half your take-home/)).toBeNull()
  })

  it('says a household cannot cover its essentials, when it cannot', () => {
    setQuery({
      // 1,560 committed and 1,296 of it essential, out of 1,200 taken home:
      // Required 130%, essentials 108%.
      data: {
        ...tiered,
        avg_monthly_cost_of_living: 1560,
        avg_monthly_essentials: 1296,
        avg_monthly_income: 1200,
      },
    })
    renderReport(<CostOfLivingReport budgetId="b1" />)
    // The worse fact, said as itself rather than as "no headroom".
    expect(screen.getByText(/costs more than you take home/i)).toBeInTheDocument()
  })

  it('shows no Essentials figure until something is tagged Essential', () => {
    // Only Cost of living tagged: the server serves the lean tier as unknown
    // rather than the whole burn rate, so nothing may read "could not be cut"
    // and the underwater sentence cannot fire on spending that could be cut.
    setQuery({
      data: {
        ...tiered,
        avg_monthly_essentials: null,
        avg_monthly_cost_of_living: 1560,
        avg_monthly_income: 1200,
      },
    })
    renderReport(<CostOfLivingReport budgetId="b1" />)
    expect(screen.getByText('nothing tagged Essential')).toBeInTheDocument()
    expect(screen.getByText('needs Essentials tagged')).toBeInTheDocument()
    expect(screen.queryByText('could not be cut')).toBeNull()
    expect(screen.queryByText(/costs more than you take home/i)).toBeNull()
  })
})

describe('DiscretionaryReport', () => {
  // Two complete months of the household test_discretionary.py builds:
  // Everyday 500 (Dining Out 450, Coffee 50), Fun 150 and 75 unfiled —
  // 725 in all, of 2,900 spent. Figures invented and round.
  const report = {
    months: ['2026-07-01', '2026-08-01'],
    months_averaged: 2,
    window_start: '2026-07-01',
    window_end: '2026-08-31',
    basis: 'tag' as const,
    tagged: true,
    total: 725,
    avg_monthly: 362.5,
    monthly_totals: [300, 425],
    spending_total: 2900,
    // Cost of living over the same two months, 3,000 of it in all.
    cost_of_living_total: 3000,
    groups: [
      {
        group_id: 'g-everyday',
        group_name: 'Everyday',
        total: 500,
        avg_monthly: 250,
        categories: [
          { category_id: 'c-dining', category_name: 'Dining Out', total: 450, avg_monthly: 225 },
          { category_id: 'c-coffee', category_name: 'Coffee', total: 50, avg_monthly: 25 },
        ],
      },
      {
        group_id: 'g-fun',
        group_name: 'Fun',
        total: 150,
        avg_monthly: 75,
        categories: [
          { category_id: 'c-hobbies', category_name: 'Hobbies', total: 150, avg_monthly: 75 },
        ],
      },
      { group_id: null, group_name: 'Uncategorized', total: 75, avg_monthly: 37.5, categories: [] },
    ],
  }

  afterEach(() => useReportStore.setState({ drillDown: null }))

  it('prints the average, the window total and the share of spending', () => {
    setQuery({ data: report })
    renderReport(<DiscretionaryReport budgetId="b1" />)

    expect(card('Discretionary')).toEqual({
      value: '$362.50',
      sub: 'per month, over 2 complete months',
    })
    expect(card('Window total').value).toBe('$725.00')
    // 725 of 2,900, composed on the page from two served figures — and said
    // per month beside a per-month headline: it read "of $2,900.00 spent",
    // the window's total.
    expect(card('Share of spending')).toEqual({ value: '25%', sub: 'of $1,450.00/mo spent' })
  })

  it('says how the tiers and spending fit, per month', () => {
    // 1,500 + 362.50 = 1,862.50: 1,450 spent and 412.50 of debt payments.
    setQuery({ data: report })
    renderReport(<DiscretionaryReport budgetId="b1" />)
    expect(
      screen.getByText(
        'Cost of living $1,500.00 + Discretionary $362.50 = $1,450.00 spent + $412.50 debt payments, a month'
      )
    ).toBeInTheDocument()
  })

  it('lists each category under its group, and unfiled spending on its own line', () => {
    setQuery({ data: report })
    renderReport(<DiscretionaryReport budgetId="b1" />)

    const table = screen.getByRole('table', { name: 'Discretionary spending by category' })
    const lines = within(table)
      .getAllByRole('button')
      .map((b) => b.textContent)
    expect(lines).toEqual(['Everyday', 'Dining Out', 'Coffee', 'Fun', 'Hobbies', 'Uncategorized'])
    expect(cellsOf('Dining Out')).toEqual(['Dining Out', '$225.00', '$450.00', '62%'])
    expect(cellsOf('Uncategorized')).toEqual(['Uncategorized', '$37.50', '$75.00', '10%'])
    // The foot is the headline, so the column adds up to what the card says.
    const foot = Array.from(table.querySelectorAll('tfoot td')).map((td) => td.textContent)
    expect(foot).toEqual(['Total', '$362.50', '$725.00', ''])
  })

  it('opens a category with the report’s own predicate over its window', () => {
    setQuery({ data: report })
    renderReport(<DiscretionaryReport budgetId="b1" />)

    fireEvent.click(screen.getByRole('button', { name: 'Show the transactions behind Dining Out' }))
    expect(useReportStore.getState().drillDown).toMatchObject({
      label: 'Dining Out',
      scope: 'leaf',
      categoryIds: ['c-dining'],
      discretionary: true,
      startDate: '2026-07-01',
      endDate: '2026-08-31',
    })
  })

  it('opens the Uncategorized line by "no category", never by an empty id list', () => {
    setQuery({ data: report })
    renderReport(<DiscretionaryReport budgetId="b1" />)

    fireEvent.click(
      screen.getByRole('button', { name: 'Show the transactions behind Uncategorized' })
    )
    const drill = useReportStore.getState().drillDown
    expect(drill).toMatchObject({ noCategory: true, discretionary: true })
    expect(drill?.categoryIds).toBeUndefined()
  })

  it('shows no number until something is tagged, and says where to tag', () => {
    setQuery({
      data: {
        ...report,
        basis: 'all',
        tagged: false,
        total: null,
        avg_monthly: null,
        monthly_totals: [],
        spending_total: null,
        groups: [],
      },
    })
    renderReport(<DiscretionaryReport budgetId="b1" />)

    expect(screen.getByText(/Nothing carries either tag yet/)).toBeInTheDocument()
    const link = screen.getByRole('link', { name: /Tag your committed categories/ })
    expect(link).toHaveAttribute('href', '/settings/tags')
    // No figure anywhere: no cards, no table.
    expect(document.querySelector('.metric-card')).toBeNull()
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.queryByText(/\$/)).toBeNull()
  })

  it('says so when everything spent was tagged', () => {
    setQuery({
      data: { ...report, total: 0, avg_monthly: 0, monthly_totals: [0, 0], groups: [] },
    })
    renderReport(<DiscretionaryReport budgetId="b1" />)
    expect(screen.getByText(/No discretionary spending in this window/)).toBeInTheDocument()
  })
})

describe('drill tables read spending as a positive figure', () => {
  // DrillDownTable stopped taking Math.abs, and five callers stopped negating
  // their figure on the way in. A caller that kept `amount: -c.spent` would
  // print -$450.00 under a Spent column and drive the footer negative.
  const noMinus = (label: string, amount: string) => {
    const cells = cellsOf(label)
    expect(cells).toContain(amount)
    expect(cells.some((c) => c.startsWith('-'))).toBe(false)
  }

  it('Income vs Expenses', () => {
    setQuery({
      data: {
        months: [
          {
            month: '2026-08-01',
            partial_month: false,
            income: 2000,
            expenses: 300,
            savings: 0,
            debt_principal: 0,
            net: 1700,
          },
        ],
      },
    })
    renderReport(<IncomeExpenseReport budgetId="b1" />)
    noMinus('Aug 26', '$300.00')
  })

  it('Pareto', () => {
    setQuery({
      data: {
        groups: [
          {
            id: 'c1',
            name: 'Rent',
            total: 500,
            count: 1,
            pct: 50,
            parent_id: 'g1',
            parent_name: 'Home',
          },
        ],
        total: 500,
      },
    })
    renderReport(<ParetoReport budgetId="b1" />)
    noMinus('Rent', '$500.00')
  })

  it('Payee Analysis', () => {
    setQuery({
      data: {
        payees: [
          {
            payee_id: 'p1',
            payee_name: 'Harborstone Market',
            total: 120,
            count: 2,
            pct: 100,
            monthly_trend: [],
            top_categories: [],
            is_recurring: false,
          },
        ],
        total: 120,
        payee_count: 1,
        payees_to_80pct: 1,
      },
    })
    renderReport(<PayeeReport budgetId="b1" />)
    noMinus('Harborstone Market', '$120.00')
  })

  it('Volatility', () => {
    setQuery({
      data: {
        categories: [
          {
            category_id: 'c1',
            category_name: 'Groceries',
            category_group_name: 'Everyday',
            mean: 400,
            std_dev: 20,
            min_val: 380,
            max_val: 420,
            p25: 390,
            p75: 410,
            months_included: 6,
          },
        ],
        amortized: false,
        window_start: '2026-03-01',
        window_end: '2026-08-31',
      },
    })
    renderReport(<VolatilityReport budgetId="b1" />)
    noMinus('Groceries', '$400.00')
  })
})

describe('EssentialsReport table footer', () => {
  it('totals its own column, not the rounded average times the months', () => {
    // Two categories of $10.00 over three months: each averages $3.33 and the
    // lean month $6.67, and $6.67 × 3 is $20.01 under a column adding to $20.00.
    setQuery({
      data: {
        tagged: true,
        months: 3,
        window_start: '2026-06-01',
        window_end: '2026-08-31',
        months_averaged: 3,
        essentials: { as_paid: 6.67, spread: 6.67, spread_on: true, monthly: 6.67 },
        monthly_total_average: 6.67,
        categories: [
          {
            category_id: 'c1',
            name: 'Water',
            group_name: 'Bills',
            total: 10,
            monthly_average: 3.33,
            months_with_spend: 3,
          },
          {
            category_id: 'c2',
            name: 'Power',
            group_name: 'Bills',
            total: 10,
            monthly_average: 3.33,
            months_with_spend: 3,
          },
        ],
        monthly_series: [],
        reserve: [],
        roadmap_range: [3, 6],
        emergency_fund: {
          set_up: false,
          total: null,
          categories: [],
          accounts: [],
          external: { declared: false, amount: null, as_of: null, note: null },
        },
        fund_runway: runwayFigure({ money: 'fund', money_total: null, months: null }),
        class_excluded: [],
      },
    })
    renderReport(<EssentialsReport budgetId="b1" />)
    const footer = screen.getByText('All essentials').closest('tr')
    expect(footer).toHaveTextContent('$20.00')
    expect(footer).not.toHaveTextContent('$20.01')
  })

  it('names the months it divided by, not the setting, on a young budget', () => {
    // "All time" on a budget three complete months old: the table averaged
    // three, and said "the last 12" — or the last 4 — beside it.
    setQuery({
      data: {
        tagged: true,
        months: 12,
        window_start: '2026-06-01',
        window_end: '2026-08-31',
        months_averaged: 3,
        essentials: { as_paid: 1200, spread: 1200, spread_on: false, monthly: 1200 },
        monthly_total_average: 1200,
        categories: [
          {
            category_id: 'c1',
            name: 'Rent',
            group_name: 'Bills',
            total: 3600,
            monthly_average: 1200,
            months_with_spend: 3,
          },
        ],
        monthly_series: [],
        reserve: [],
        roadmap_range: [3, 6],
        emergency_fund: {
          set_up: false,
          total: null,
          categories: [],
          accounts: [],
          external: { declared: false, amount: null, as_of: null, note: null },
        },
        fund_runway: runwayFigure({ money: 'fund', money_total: null, months: null }),
        class_excluded: [],
      },
    })
    renderReport(<EssentialsReport budgetId="b1" />)
    expect(screen.getByText(/The table averages the last/)).toHaveTextContent(
      'The table averages the last 3 complete months'
    )
    expect(screen.getByText('Rent').closest('tr')).toHaveTextContent('3/3')
    expect(screen.queryByText(/last 12/)).not.toBeInTheDocument()
  })
})

describe('EssentialsReport headline', () => {
  const report = (essentials: object, over: object = {}) => ({
    tagged: true,
    months: 12,
    window_start: '2025-09-01',
    window_end: '2026-08-31',
    months_averaged: 12,
    essentials: { window_start: '2026-06-01', window_end: '2026-08-31', ...essentials },
    long_term_essentials: 1,
    monthly_total_average: 2000,
    categories: [],
    monthly_series: [],
    reserve: [],
    roadmap_range: [3, 6],
    emergency_fund: {
      set_up: false,
      total: null,
      categories: [],
      accounts: [],
      external: { declared: false, amount: null, as_of: null, note: null },
    },
    fund_runway: runwayFigure({ money: 'fund', money_total: null, months: null }),
    class_excluded: [],
    ...over,
  })

  it('headlines the figure the setting picks and names the other', () => {
    setQuery({
      data: report({ as_paid: 2800, spread: 2200, spread_on: false, monthly: 2800 }),
    })
    renderReport(<EssentialsReport budgetId="b1" />)
    // The months it averages, then the other figure on a line of its own.
    expect(card('Essentials / month')).toEqual({
      value: '$2,800.00',
      sub: 'Jun 26 – Aug 26 average$2,800.00/mo as paid · $2,200.00/mo spread',
    })
    expect(
      screen.getByRole('checkbox', { name: 'Spread yearly bills over 12 months' })
    ).toBeInTheDocument()
  })

  it('keeps its window as the sub-line when the two agree', () => {
    // It read "90-day average": the window is three complete months (D6),
    // and the card names them.
    setQuery({ data: report({ as_paid: 2000, spread: 2000, spread_on: true, monthly: 2000 }) })
    renderReport(<EssentialsReport budgetId="b1" />)
    expect(card('Essentials / month')).toEqual({
      value: '$2,000.00',
      sub: 'Jun 26 – Aug 26 average',
    })
  })

  it('says there is nothing to spread instead of offering the switch', () => {
    setQuery({
      data: report(
        { as_paid: 2000, spread: 2000, spread_on: true, monthly: 2000 },
        { long_term_essentials: 0 }
      ),
    })
    renderReport(<EssentialsReport budgetId="b1" />)
    expect(screen.queryByRole('checkbox')).toBeNull()
    expect(screen.getByText(/No Essential category is also a Long-term expense/)).toBeTruthy()
  })

  it('collapses the reserve sizes into one line of targets', () => {
    // Four cards of headline × N crowded out the three figures that are not
    // arithmetic on it.
    setQuery({
      data: report(
        { as_paid: 2000, spread: 2000, spread_on: true, monthly: 2000 },
        {
          reserve: [
            { months: 1, amount: 2000 },
            { months: 3, amount: 6000 },
            { months: 6, amount: 12000 },
            { months: 12, amount: 24000 },
          ],
        }
      ),
    })
    renderReport(<EssentialsReport budgetId="b1" />)
    expect(screen.queryByText('3-month reserve')).toBeNull()
    expect(document.querySelector('.essentials-report__targets')?.textContent).toBe(
      'Targets1 month $2,000.00 · 3 months $6,000.00 · 6 months $12,000.00 · 12 months $24,000.00 — the roadmap suggests 3–6'
    )
  })

  it('says how far the worst month ran over the headline', () => {
    // It read "Sep 2025 — ×6 reserve: $X": a reserve nobody sizes from one
    // bad month.
    setQuery({
      data: report(
        { as_paid: 2000, spread: 2000, spread_on: true, monthly: 2000 },
        {
          monthly_series: [
            { month: '2026-07-01', total: 2500, sinking_total: 0 },
            { month: '2026-08-01', total: 1900, sinking_total: 0 },
          ],
        }
      ),
    })
    renderReport(<EssentialsReport budgetId="b1" />)
    expect(card('Worst month')).toEqual({
      value: '$2,500.00',
      sub: 'Jul 26 · 25% over the headline',
    })
  })
})

describe('EmergencyCoverageReport', () => {
  const pt = (month: string, coverage: number | null, counted = false) => ({
    month,
    fund_balance: 4000,
    essentials: 1000,
    coverage_months: coverage,
    target_low: 3000,
    target_high: 6000,
    external_counted: counted,
  })
  const base = {
    months: 12,
    tagged: true,
    fund: {
      set_up: true,
      total: 4000,
      categories: [],
      accounts: [{ id: 'a1', name: 'Cascade Point HYSA', balance: 4000 }],
      external: { declared: false, amount: null, as_of: null, note: null },
    },
    covered: runwayFigure({ money: 'fund', money_total: 4000, card_debt: 0, months: 4 }),
    essentials: {
      as_paid: 1000,
      spread: 1000,
      spread_on: true,
      monthly: 1000,
      window_start: '2026-06-01',
      window_end: '2026-08-31',
    },
    long_term_essentials: 1,
    target_low: 3000,
    target_high: 6000,
    target_range: [3, 6],
    external_amount: null,
    external_as_of: null,
    current_month: '2026-09-01',
  }

  it('names the month the self-reported fund is counted from, not the day it was saved', () => {
    // Saved on 2026-09-11. The series ends at August, the only point that
    // counts the figure; the note said "carried flat from September 2026".
    setQuery({
      data: {
        ...base,
        series: [pt('2026-07-01', 3), pt('2026-08-01', 4, true)],
        external_amount: 4000,
        external_as_of: '2026-09-11',
      },
    })
    renderReport(<EmergencyCoverageReport budgetId="b1" />)
    expect(screen.getByText(/carried flat from Aug 26/)).toBeInTheDocument()
    expect(screen.queryByText(/Sep 26/)).toBeNull()
    // Both charts say they end at the last complete month.
    expect(screen.getByText('Months covered, through Aug 26')).toBeInTheDocument()
    expect(screen.getByText('Fund against a moving target, through Aug 26')).toBeInTheDocument()
  })

  it('states the span of a trend with a gap inside it', () => {
    setQuery({
      data: {
        ...base,
        series: [
          pt('2026-01-01', 2),
          pt('2026-02-01', null),
          pt('2026-03-01', null),
          pt('2026-04-01', 4),
        ],
      },
    })
    renderReport(<EmergencyCoverageReport budgetId="b1" />)
    expect(screen.getByText('up 2 months in 4 months')).toBeInTheDocument()
  })

  it('reads the spread figure and names the as-paid one beside it', () => {
    setQuery({
      data: {
        ...base,
        essentials: {
          as_paid: 2800,
          spread: 2200,
          spread_on: true,
          monthly: 2200,
          window_start: '2026-06-01',
          window_end: '2026-08-31',
        },
        series: [pt('2026-08-01', 4)],
      },
    })
    renderReport(<EmergencyCoverageReport budgetId="b1" />)
    expect(
      screen.getByText(
        /\$2,200\.00\/month, the average of Jun 26 – Aug 26, with yearly bills spread/
      )
    ).toHaveTextContent('($2,200.00/mo spread · $2,800.00/mo as paid)')
    expect(
      screen.getByRole('checkbox', { name: 'Spread yearly bills over 12 months' })
    ).toBeChecked()
  })

  it('says nothing more when the two figures agree', () => {
    setQuery({ data: { ...base, series: [pt('2026-08-01', 4)] } })
    renderReport(<EmergencyCoverageReport budgetId="b1" />)
    expect(screen.queryByText(/\/mo as paid/)).toBeNull()
  })

  it('reads Covered as the runway rule: the fund, cards paid, with its date', () => {
    // 4,000 of fund less 500 owed is 3.5 months at 1,000 — the chart's newest
    // point is the fund alone, and the note says why the two differ.
    setQuery({
      data: {
        ...base,
        covered: runwayFigure({
          money: 'fund',
          money_total: 3500,
          card_debt: 500,
          months: 3.5,
          runs_out_on: '2027-01-11',
        }),
        series: [pt('2026-08-01', 4)],
      },
    })
    renderReport(<EmergencyCoverageReport budgetId="b1" />)
    expect(card('Covered').value).toBe('3.5 months')
    expect(card('Covered').sub).toMatch(/^to Jan 11, 2027/)
    expect(screen.getByText(/less \$500\.00 owed on your credit cards/)).toBeInTheDocument()
  })
})

describe('info panels say what the chart draws', () => {
  const openInfo = (name: string) =>
    fireEvent.click(screen.getByRole('button', { name: `About the ${name} report` }))

  it('Net Worth: overlaid areas, debts subtracted, stated assets counted', () => {
    // It said "The stacked area shows…" over areas drawn on top of each other,
    // "plus any manually tracked debts" of debts it subtracts, and never
    // mentioned the stated asset values it adds.
    setQuery({
      data: {
        points: [],
        change: 0,
        like_for_like_change: null,
        entered_total: 0,
        stated_values: [],
        stale_balances: [],
        stale_after_days: 60,
      },
    })
    renderReport(<NetWorthReport budgetId="b1" />)
    openInfo('Net Worth Over Time')
    expect(screen.getByText(/not stacked/)).toBeInTheDocument()
    expect(screen.getByText(/stated value of things/)).toBeInTheDocument()
    expect(screen.getByText(/both are subtracted/)).toBeInTheDocument()
    expect(screen.queryByText(/stacked area/)).toBeNull()
    expect(screen.queryByText(/plus any manually tracked debts/)).toBeNull()
  })

  it('Income vs Expenses: series by legend name, never by a colour the theme may not use', () => {
    setQuery({ data: { months: [] } })
    renderReport(<IncomeExpenseReport budgetId="b1" />)
    openInfo('Income vs Expenses')
    expect(screen.getAllByText(/Net line/).length).toBeGreaterThan(0)
    expect(screen.queryByText(/\b(blue|green|red)\b/)).toBeNull()
  })

  it('Income vs Expenses: Net is how much the budget accounts grew, not "cash flow"', () => {
    setQuery({ data: { months: [] } })
    renderReport(<IncomeExpenseReport budgetId="b1" />)
    openInfo('Income vs Expenses')
    expect(screen.getByText(/how much your budget accounts grew/)).toBeInTheDocument()
    // "Below zero, you ran a deficit" was wrong for a month that moved money
    // into a brokerage: Net falls, and nothing was spent.
    expect(
      screen.getByText(/moving money into savings or investments lowers Net/)
    ).toBeInTheDocument()
    expect(screen.queryByText(/cash flow/i)).toBeNull()
  })

  it('Overview: which cards follow the range, and which are as of today', () => {
    // "All metrics use the selected date range except burn rates" — while Net
    // Worth, Essentials and the runway card were as of today too.
    setQuery({
      data: {
        net_worth: 0,
        burn_rate_30: 0,
        burn_rate_prior_60: 0,
        income_this_month: 0,
        outflows_this_month: 0,
        top_categories: [],
        means_months: [],
        runway: overviewRunway(),
      },
    })
    renderReport(<OverviewReport budgetId="b1" />)
    openInfo('Overview Dashboard')
    expect(screen.getByText(/follows the date range/)).toBeInTheDocument()
    expect(screen.getByText(/does not\s+move with the range/)).toBeInTheDocument()
    expect(screen.queryByText(/All metrics use the selected date range/)).toBeNull()
    // It said the Essentials card was "those same 90 days"; it is three
    // complete months (D6), and the burn ends yesterday.
    expect(screen.queryByText(/90 days/)).toBeNull()
  })

  it('Overview: groups the cards into this period and now, and says "so far"', () => {
    setQuery({
      data: {
        net_worth: 0,
        burn_rate_30: 0,
        burn_rate_prior_60: 0,
        income_this_month: 0,
        outflows_this_month: 0,
        top_categories: [],
        means_months: [],
        runway: overviewRunway(),
      },
    })
    const saved = useReportStore.getState().filters
    const t = today()
    useReportStore.setState({ filters: { ...saved, startDate: `${t.slice(0, 7)}-01`, endDate: t } })
    renderReport(<OverviewReport budgetId="b1" />)
    const headings = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent)
    expect(headings[0]).toMatch(/^This period · \w{3} \d{2} so far$/)
    expect(headings[1]).toBe('Now')
    useReportStore.setState({ filters: saved })
  })
})

describe('AccountCompositionReport info panel', () => {
  it('explains the Net line without a note about its own earlier wording', () => {
    // The panel ended '(An unmanaged debt REDUCES net worth; this said "plus".)'
    // — a changelog entry shown to a reader who never saw the old copy.
    setQuery({ data: { points: [], series: [] } })
    renderReport(<AccountCompositionReport budgetId="b1" />)
    fireEvent.click(screen.getByRole('button', { name: 'About the Account Composition report' }))
    // The stack now holds stated values and hand-tracked debts as bands of
    // their own, so the Net line is the stack's sum — no "less" or "plus".
    expect(screen.getByText(/sum of every band/)).toBeInTheDocument()
    expect(screen.getAllByText(/debts tracked by hand/).length).toBeGreaterThan(0)
    expect(screen.queryByText(/this said/)).toBeNull()
  })
})

/**
 * One meaning of spending: every spending chart drills with the classes the
 * server says it counted, in both directions — the figures are net of
 * refunds — and opens the Uncategorized line by "no category". A client copy
 * of the class set (`spendingDrillClasses`) and `direction: 'outflow'` on
 * every drill made each list longer than the bar above it by its refunds.
 */
describe('spending drills total what the chart totals', () => {
  const served = ['spending', 'savings', 'debt_principal']
  const grouped = {
    groups: [
      {
        id: 'c1',
        name: 'Groceries',
        parent_id: 'g1',
        parent_name: 'Everyday',
        total: 250,
        count: 3,
        pct: 86.2,
      },
      {
        id: null,
        name: 'Uncategorized',
        parent_id: null,
        parent_name: 'Uncategorized',
        total: 40,
        count: 1,
        pct: 13.8,
      },
    ],
    total: 290,
    view_hidden_categories: 0,
    view_hidden_total: 0,
    class_excluded: [],
    filter_unavailable: false,
    counted_classes: served,
  }

  afterEach(() => {
    useReportStore.getState().setDrillDown(null)
    useReportStore.getState().setFilters({ groupBy: 'group', categoryIds: [] })
  })

  const drill = () => useReportStore.getState().drillDown

  it('Breakdown used to omit the Uncategorized line; it opens by "no category"', () => {
    setQuery({ data: grouped })
    renderReport(<SpendingBreakdownReport budgetId="b1" />)
    const cell = () => screen.getAllByText('Uncategorized').find((el) => el.tagName === 'TD')!
    fireEvent.click(cell()) // the group
    fireEvent.click(cell()) // its one line
    expect(drill()).toMatchObject({ noCategory: true, activityClasses: served })
    expect(drill()?.categoryIds).toBeUndefined()
    expect(drill()?.direction).toBeUndefined()
  })

  it('Breakdown lists a line that netted negative, and leaves it off the ring', () => {
    setQuery({
      data: {
        ...grouped,
        groups: [
          ...grouped.groups,
          {
            id: 'c9',
            name: 'Returns',
            parent_id: 'g9',
            parent_name: 'Shopping',
            total: -90,
            count: 1,
            pct: 0,
          },
        ],
        total: 200,
      },
    })
    renderReport(<SpendingBreakdownReport budgetId="b1" />)
    expect(cellsOf('Shopping')).toContain('-$90.00')
    expect(screen.getByText(/Refunds outweighed spending on 1 line/)).toBeInTheDocument()
  })

  it('Seasonality opens a cell with the served classes, uncategorized by "no category"', () => {
    setQuery({
      data: {
        months: ['2026-07-01'],
        categories: [{ id: null, name: 'Uncategorized' }],
        cells: [{ category_id: null, month: '2026-07-01', total: 40 }],
        category_count: 1,
        counted_classes: ['spending'],
      },
    })
    const { container } = renderReport(<SeasonalityReport budgetId="b1" />)
    fireEvent.click(container.querySelector('td.heatmap__cell--clickable')!)
    expect(drill()).toMatchObject({
      noCategory: true,
      activityClasses: ['spending'],
      startDate: '2026-07-01',
      endDate: '2026-07-31',
    })
    expect(drill()?.direction).toBeUndefined()
  })

  it('Seasonality says how many categories it cut the grid from', () => {
    setQuery({
      data: {
        months: ['2026-07-01'],
        categories: [{ id: 'c1', name: 'Electric' }],
        cells: [{ category_id: 'c1', month: '2026-07-01', total: 90 }],
        category_count: 34,
        counted_classes: ['spending'],
      },
    })
    renderReport(<SeasonalityReport budgetId="b1" />)
    expect(screen.getByText(/The top 1 of 34 categories/)).toBeInTheDocument()
  })

  it('Payees open leaf rows of the served classes, refunds included', () => {
    setQuery({
      data: {
        payees: [
          {
            payee_id: 'p1',
            payee_name: 'Corner Market',
            total: 250,
            count: 2,
            pct: 100,
            monthly_trend: [],
            top_categories: [],
            is_recurring: false,
          },
        ],
        total: 250,
        payee_count: 1,
        payees_to_80pct: 1,
        recurring_min_months: 3,
        counted_classes: ['spending'],
      },
    })
    renderReport(<PayeeReport budgetId="b1" />)
    fireEvent.click(screen.getAllByText('Corner Market').at(-1)!)
    expect(drill()).toMatchObject({
      payeeIds: ['p1'],
      scope: 'leaf',
      activityClasses: ['spending'],
    })
    expect(drill()?.direction).toBeUndefined()
    // "Occasional", not "One-off", and the rule the server applied.
    expect(screen.getByText('Occasional')).toBeInTheDocument()
    expect(
      screen.getAllByText(/Recurring = seen in 3\+ months of the range/).length
    ).toBeGreaterThan(0)
  })

  it('Pareto payee mode carries no category scope, which its report never applied', () => {
    useReportStore.getState().setFilters({ groupBy: 'payee', categoryIds: ['c1'] })
    setQuery({
      data: {
        ...grouped,
        payees: [
          {
            payee_id: 'p1',
            payee_name: 'Corner Market',
            total: 250,
            count: 2,
            pct: 100,
            monthly_trend: [],
            top_categories: [],
            is_recurring: false,
          },
        ],
        payee_count: 1,
        payees_to_80pct: 1,
        recurring_min_months: 3,
      },
    })
    renderReport(<ParetoReport budgetId="b1" />)
    fireEvent.click(screen.getAllByText('Corner Market').at(-1)!)
    expect(drill()).toMatchObject({ payeeIds: ['p1'], activityClasses: served })
    expect(drill()?.categoryIds).toBeUndefined()
    expect(drill()?.direction).toBeUndefined()
  })

  it('the Pareto and Seasonality panels name no colours', () => {
    // A colour name is wrong in thirty-nine of forty themes.
    setQuery({ data: grouped })
    renderReport(<ParetoReport budgetId="b1" />)
    fireEvent.click(screen.getByRole('button', { name: 'About the Pareto Analysis report' }))
    expect(screen.queryByText(/\b(orange|red|blue|green)\b/)).toBeNull()
  })

  it('Seasonality panel names no colours either', () => {
    setQuery({ data: { months: [], categories: [], cells: [], category_count: 0 } })
    renderReport(<SeasonalityReport budgetId="b1" />)
    fireEvent.click(screen.getByRole('button', { name: 'About the Seasonality Heatmap report' }))
    expect(screen.queryByText(/\b(orange|red|blue|green)\b/)).toBeNull()
  })
})

describe('Spending Trends cards', () => {
  it('averages complete months and calls the running one "so far"', () => {
    // It divided the window by every month on the axis, the running one
    // included, and called that month "Latest month".
    setQuery({
      data: {
        months: ['2026-08-01', '2026-09-01'],
        series: [
          {
            id: 'c1',
            name: 'Groceries',
            group_id: 'g1',
            group_name: 'Everyday',
            monthly: [300, 120],
            total: 420,
          },
        ],
        monthly_totals: [300, 120],
        total: 420,
        avg_monthly: 300,
        months_averaged: 1,
        running_month: '2026-09-01',
        class_excluded: [],
        filter_unavailable: false,
        counted_classes: ['spending'],
      },
    })
    renderReport(<SpendingTrendsReport budgetId="b1" />)
    expect(card('Average / month')).toEqual({
      value: '$300.00',
      sub: 'per month, over 1 complete month',
    })
    expect(screen.getByText(/so far$/, { selector: '.metric-card__label' })).toBeInTheDocument()
    expect(screen.queryByText('Latest month')).toBeNull()
  })
})

describe('Largest transactions', () => {
  it('is titled for what it lists, with no card restating the row count', () => {
    setQuery({
      data: {
        transactions: [
          {
            id: 't1',
            date: '2026-09-03',
            amount: -1400,
            payee_name: 'Harborstone',
            category_name: 'Rent',
            memo: null,
            activity_class: 'spending',
            activity_label: 'Spending',
          },
        ],
        filter_unavailable: false,
      },
    })
    renderReport(<TimelineReport budgetId="b1" />)
    expect(screen.getByRole('heading', { name: 'Largest transactions' })).toBeInTheDocument()
    expect(screen.queryByText('Shown')).toBeNull()
    // Money out is the default view.
    expect(screen.getByRole('button', { name: 'Money out' })).toHaveClass('report-btn--active')
    // A formatted date, not the ISO string.
    expect(screen.queryByText('2026-09-03')).toBeNull()
  })
})

describe('AnomaliesReport reading', () => {
  const row = {
    group_name: 'Everyday',
    actual: 300,
    baseline_mean: 100,
    usual_low: 80,
    usual_high: 120,
    z_score: 10,
    direction: 'high',
    partial_month: false,
    history: [null, null, 100, 0, 120, 300],
  }

  it('lists the newest month first and says what "usual" was', () => {
    setQuery({
      data: {
        anomalies: [
          { ...row, category_id: 'c1', category_name: 'Gifts', month: '2026-05-01', z_score: 9 },
          { ...row, category_id: 'c2', category_name: 'Dining', month: '2026-08-01', z_score: 3 },
        ],
        categories_seen: 2,
        categories_tested: 2,
        sinking_funds_skipped: 0,
      },
    })
    renderReport(<AnomaliesReport budgetId="b1" />)

    const labels = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent)
    expect(labels[0]).toMatch(/Aug 26/)
    expect(labels[1]).toMatch(/May 26/)
    expect(screen.getAllByText('$80.00–$120.00')).toHaveLength(2)
    expect(screen.getAllByText('usually')).toHaveLength(2)
  })

  it('says how many categories an empty report tested', () => {
    setQuery({
      data: {
        anomalies: [],
        categories_seen: 22,
        categories_tested: 14,
        sinking_funds_skipped: 1,
      },
    })
    renderReport(<AnomaliesReport budgetId="b1" />)

    expect(
      screen.getByText(/14 of 22 categories had six earlier months to test against\./)
    ).toBeInTheDocument()
    expect(screen.getByText(/1 sinking fund is not tested/)).toBeInTheDocument()
  })
})

describe('VolatilityReport table', () => {
  const stats = (id: string, name: string, mean: number, sd: number) => ({
    category_id: id,
    category_name: name,
    category_group_name: 'Everyday',
    mean,
    std_dev: sd,
    min_val: 0,
    max_val: mean * 2,
    p25: 0,
    p75: mean,
    months_included: 6,
  })

  it('ranks by swing, names its columns, and states its window', () => {
    // Largest average first put the steady mortgage on top, under columns
    // headed "%" and "Extra".
    setQuery({
      data: {
        categories: [
          stats('m', 'Mortgage', 1500, 15),
          stats('g', 'Gifts', 100, 120),
          stats('f', 'Fuel', 200, 60),
        ],
        amortized: false,
        window_start: '2025-09-01',
        window_end: '2026-08-31',
      },
    })
    const { container } = renderReport(<VolatilityReport budgetId="b1" />)

    const names = [...container.querySelectorAll('.ddt__name')].map((n) => n.textContent)
    expect(names).toEqual(['Gifts', 'Fuel', 'Mortgage'])
    expect(screen.getByRole('columnheader', { name: 'Swing' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'σ' })).toBeInTheDocument()
    expect(screen.getByText(/Complete months, September 2025 – August 2026/)).toBeInTheDocument()
  })
})

/**
 * Net Worth: the headline is like-for-like, and what began being counted is
 * named — the audit's year read +$620k on the chart and was slightly down.
 */
describe('NetWorthReport, where counting began', () => {
  const point = (date: string, net: number, entries: unknown[] = []) => ({
    date,
    total_assets: Math.max(net, 0),
    total_liabilities: 0,
    net_worth: net,
    unmanaged_liability_total: 0,
    asset_value_total: 0,
    accounts: [],
    entered: (entries as { amount: number }[]).reduce((sum, e) => sum + e.amount, 0),
    entries,
  })
  const house = {
    kind: 'stated_asset',
    id: 'h',
    name: 'Maple St House',
    day: '2026-08-03',
    amount: 300000,
  }
  const report = {
    points: [
      point('2026-07-01', 18600),
      point('2026-08-01', 318900, [house]),
      point('2026-09-01', 319000),
    ],
    change: 300400,
    like_for_like_change: 400,
    entered_total: 300000,
    stated_values: [
      {
        kind: 'stated_asset',
        id: 'h',
        name: 'Maple St House',
        value: 300000,
        as_of: '2026-08-03',
      },
    ],
    stale_balances: [
      { kind: 'account', id: 'a', name: 'Harborstone Checking', last_changed: '2026-07-10' },
    ],
    stale_after_days: 60,
    unmanaged_liability_total: 0,
    asset_value_total: 300000,
  }

  it('leads with the like-for-like change and says what it leaves out', () => {
    setQuery({ data: report })
    renderReport(<NetWorthReport budgetId="b1" />)
    expect(card('Change, like-for-like')).toEqual({
      value: '+$400.00',
      sub: '+$300,400.00 on the chart · +$300,000.00 of it from tracking starting',
    })
  })

  it('keys each arrival, dates the stated value and flags the flat line', () => {
    setQuery({ data: report })
    renderReport(<NetWorthReport budgetId="b1" />)
    expect(screen.getByRole('region', { name: 'When counting began' })).toHaveTextContent(
      '1 value first stated: +$300,000.00'
    )
    expect(screen.getByText(/Maple St House as of/)).toBeInTheDocument()
    expect(
      screen.getByText(/Unchanged for 60\+ days.*Harborstone Checking \(last moved/)
    ).toBeInTheDocument()
  })
})
