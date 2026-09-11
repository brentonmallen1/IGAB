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

import { useReportStore } from '../../stores/reportStore'
import { CostOfLivingReport } from './charts/CostOfLivingReport'
import { EssentialsReport } from './charts/EssentialsReport'
import { WishlistDisciplineReport } from './charts/WishlistDisciplineReport'
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
import { IncomeSourcesReport } from './charts/IncomeSourcesReport'
import { LiabilitiesReport } from './charts/LiabilitiesReport'
import { NetWorthReport } from './charts/NetWorthChart'
import { ParetoReport } from './charts/ParetoChart'
import { PayeeReport } from './charts/PayeeChart'
import { PlanVsRealityReport } from './charts/PlanVsRealityReport'
import { SavingsReport } from './charts/SavingsReport'
import { SavingsRateReport } from './charts/SavingsRateChart'
import { SeasonalityReport } from './charts/SeasonalityHeatmap'
import { SpendingTreemapReport } from './charts/SpendingTreemap'
import { SpendingBreakdownReport } from './charts/SpendingBreakdownReport'
import { SpendingTrendsReport } from './charts/SpendingTrendsReport'
import { SubscriptionsReport } from './charts/SubscriptionsReport'
import { VarianceReport } from './charts/VarianceChart'
import { VolatilityReport } from './charts/VolatilityChart'

const ALL_REPORTS: [string, ComponentType<{ budgetId: string }>][] = [
  ['Overview', OverviewReport],
  ['CostOfLiving', CostOfLivingReport],
  ['Essentials', EssentialsReport],
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
  ['BudgetActual', BudgetActualReport],
  ['Variance', VarianceReport],
  ['Volatility', VolatilityReport],
  ['Pareto', ParetoReport],
  ['SpendingTreemap', SpendingTreemapReport],
  ['SpendingBreakdown', SpendingBreakdownReport],
  ['SpendingTrends', SpendingTrendsReport],
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
        burn_rate_30: '900',
        burn_rate_90: '850',
        savings_rate: 0.25,
        days_until_zero: 45.6,
        income_this_month: '4000',
        expenses_this_month: '3000',
        expenses_prev_month: '2500',
        top_categories: [{ id: 'c1', name: 'Groceries', group_name: 'Everyday', total: 300 }],
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

  it('asks for categories tagged Essential, not payees, before there is a figure', () => {
    // Essential is a category tag only; a payee tag counts for nothing. The
    // first-run prompt still said "Tag categories or payees Essential".
    setQuery({ data: { net_worth: '0', burn_rate_30: '0', burn_rate_90: '0', top_categories: [] } })
    renderReport(<OverviewReport budgetId="b1" />)
    expect(card('Essentials / month')).toEqual({ value: '—', sub: 'Tag categories Essential' })
  })
})

describe('SavingsReport before an import', () => {
  // An imported budget whose history could not be walked back from YNAB's
  // figure before August: those months are null — a gap, not an empty
  // envelope — and the page has to say why.
  const data = {
    categories: [
      {
        category_id: 'c1',
        category_name: 'Vacation',
        group_name: 'Goals',
        monthly_balances: [null, null, 100, 150],
        current_balance: 150,
        target_balance: null,
        total_inflow: 250,
      },
    ],
    summary: { total_balance: 150, total_inflow: 250, avg_monthly_inflow: 62.5, category_count: 1 },
    months: ['2026-06-01', '2026-07-01', '2026-08-01', '2026-09-01'],
    drains: { total: 0, moves: [] },
    unrecovered: [{ category_id: 'c1', category_name: 'Vacation', starts_from: '2026-08-01' }],
  }

  it('names the envelope that starts late, and why', () => {
    setQuery({ data })
    renderReport(<SavingsReport budgetId="b1" />)
    const note = screen.getByText(/Vacation starts in/)
    expect(note).toHaveTextContent(/doesn.t reproduce YNAB.s balance/)
  })

  it('says nothing when every month has a figure', () => {
    setQuery({ data: { ...data, unrecovered: [] } })
    renderReport(<SavingsReport budgetId="b1" />)
    expect(screen.queryByText(/reproduce YNAB/)).not.toBeInTheDocument()
  })
})

describe('SubscriptionsReport table', () => {
  it('shows BOTH the per-charge and normalized monthly columns', () => {
    setQuery({
      data: {
        subscriptions: [
          {
            category_id: 'c1',
            category_name: 'Fitness',
            group_name: 'Wellbeing',
            monthly_amounts: [30, 0, 0, 30],
            total: 120,
            avg_monthly: 10,
            avg_per_charge: 30,
            last_charge_date: '2026-05-01',
            transaction_count: 4,
            payees: [
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
          },
        ],
        summary: { total_monthly: 10, total_annual: 120, active_count: 1 },
        months: ['2026-02-01', '2026-03-01', '2026-04-01', '2026-05-01'],
        months_averaged: 4,
      },
    })
    renderReport(<SubscriptionsReport budgetId="b1" />)

    expect(card('Monthly').sub).toBe('effective, over 4 complete months')
    expect(screen.getByText('Per Charge')).toBeInTheDocument()
    expect(screen.getByText('Monthly (effective)')).toBeInTheDocument()
    // $30 per charge but only $10/mo effective — both perspectives visible
    expect(screen.getByText('$30.00')).toBeInTheDocument()
    expect(screen.getAllByText('$10.00').length).toBeGreaterThan(0)
    // projected annual (also the total column — both show $120.00)
    expect(screen.getAllByText('$120.00').length).toBeGreaterThan(0)
  })

  it('leads with the tagged category and opens onto its payees', () => {
    // The tag is on categories, so the category is the line. Listing payees
    // at the top level made the tag a filter and left the envelope unnamed.
    setQuery({
      data: {
        subscriptions: [
          {
            category_id: 'c1',
            category_name: 'Streaming',
            group_name: 'Bills',
            monthly_amounts: [30],
            total: 30,
            avg_monthly: 30,
            avg_per_charge: 15,
            last_charge_date: '2026-05-01',
            transaction_count: 2,
            payees: [
              {
                payee_id: 'p1',
                payee_name: 'Northwind Stream',
                monthly_amounts: [20],
                total: 20,
                avg_monthly: 20,
                avg_per_charge: 20,
                last_charge_date: '2026-05-01',
                transaction_count: 1,
              },
            ],
          },
        ],
        summary: { total_monthly: 30, total_annual: 360, active_count: 1 },
        months: ['2026-05-01'],
        months_averaged: 1,
      },
    })
    renderReport(<SubscriptionsReport budgetId="b1" />)

    expect(card('Monthly').sub).toBe('effective, over 1 complete month')

    expect(screen.getByText('Category')).toBeInTheDocument()
    const row = screen.getByRole('button', { name: /Streaming/ })
    expect(row).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('Northwind Stream')).toBeNull()

    fireEvent.click(row)

    expect(row).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('Northwind Stream')).toBeInTheDocument()
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

describe('DayPatternsReport payday baseline', () => {
  it('shows no baseline, rather than $0.00, when paydays cover every day', () => {
    // The server serves null when no day falls outside a payday window. The
    // chart turned it into 0 with `?? 0`, so the card read "Baseline Daily
    // $0.00" — "spends nothing between paydays" — and every bar with any
    // spend was painted as above it. Both hooks share this mock's data, so
    // each row carries the day-of-week fields and the payday fields.
    setQuery({
      data: {
        days: [0, 1].map((i) => ({
          day_of_week: i,
          day_name: i ? 'Tuesday' : 'Monday',
          total: 50,
          count: 1,
          avg_transaction: 50,
          offset: i,
          avg_spend: 40,
        })),
        counted_classes: ['spending'],
        baseline_daily: null,
        event_count: 26,
        payday_floor: 200,
      },
    })
    renderReport(<DayPatternsReport budgetId="b1" />)

    expect(screen.getByText('No days fall outside a payday window')).toBeInTheDocument()
    expect(screen.queryByText('Average on non-payday periods')).toBeNull()
    expect(screen.queryByText('$0.00')).toBeNull()
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
        baseline_daily: 12,
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
    expect(panel.getByText(/Counts spending only/)).toBeInTheDocument()
  })
})

describe('WishlistDisciplineReport resisted wishes', () => {
  it('counts the wishes its Resisted figure sums, and lists the early drops', () => {
    // Three wishes dropped on day three of a thirty-day wait. The card read
    // "$300.00 — 0 talked yourself out of" and the table had no row for them.
    setQuery({
      data: {
        cooled_then_bought: 0,
        cooled_then_dropped: 0,
        bought_early: 0,
        dropped_early: 3,
        still_open: 0,
        resisted_total: 300,
        resisted_count: 3,
        bought_total: 0,
        open_total: 0,
        avg_days_to_buy: null,
        avg_wish_cost: 100,
        unplaced: 0,
      },
    })
    renderReport(<WishlistDisciplineReport budgetId="b1" />)

    expect(screen.getByText('3 talked yourself out of')).toBeInTheDocument()
    const row = screen.getByText('Decided against before the wait was up').closest('tr')
    expect(row).toHaveTextContent('3')
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
    // Rent + Groceries reach 80%: 2 of 4 categories = 50% coverage, which is
    // above the 30% adherence threshold, so the spread-thin message shows
    expect(screen.getByText('2 categories')).toBeInTheDocument()
    expect(
      screen.getByText('Spending is spread thin—consider consolidating or reviewing smaller items.')
    ).toBeInTheDocument()
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

describe('PlanVsRealityReport matrix', () => {
  const planData = {
    months: ['2026-06-01', '2026-07-01', '2026-08-01'],
    categories: [
      {
        category_id: 'c1',
        category_name: 'Dining',
        category_group_name: 'Everyday',
        monthly: [
          { month: '2026-06-01', assigned: 100, spent: 140, variance: -40 },
          { month: '2026-07-01', assigned: 100, spent: 90, variance: 10 },
          { month: '2026-08-01', assigned: 0, spent: 0, variance: 0 },
        ],
        months_over: 1,
        months_active: 2,
        total_assigned: '200',
        total_spent: '230',
        avg_overspend: 40.0,
        chronic: true,
      },
      {
        category_id: 'c2',
        category_name: 'Rent',
        category_group_name: 'Home',
        monthly: [
          { month: '2026-06-01', assigned: 900, spent: 900, variance: 0 },
          { month: '2026-07-01', assigned: 900, spent: 900, variance: 0 },
          { month: '2026-08-01', assigned: 900, spent: 900, variance: 0 },
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
            assigned: 500,
            spent: 450,
            variance: 50,
            variance_pct: 10,
            overspent: false,
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

  it('reads overspent from the server, so a drained envelope is not an overrun', () => {
    // Car Repairs had 300 moved OUT and spent nothing: a negative assignment.
    // The chart used to decide `spent > assigned` itself — 0 > -300 — and kept
    // it under "Overspent only" while Plan vs Reality called it neutral.
    setQuery({
      data: {
        categories: [
          {
            category_id: 'c1',
            category_name: 'Car Repairs',
            category_group_name: 'Irregular',
            assigned: -300,
            spent: 0,
            variance: 0,
            variance_pct: 0,
            overspent: false,
          },
          {
            category_id: 'c2',
            category_name: 'Dining',
            category_group_name: 'Everyday',
            assigned: 100,
            spent: 160,
            variance: -60,
            variance_pct: -60,
            overspent: true,
          },
        ],
        total_assigned: '-200',
        total_spent: '160',
      },
    })
    renderReport(<BudgetActualReport budgetId="b1" />)

    fireEvent.click(screen.getByLabelText('Overspent only'))
    expect(screen.getByText('Dining')).toBeInTheDocument()
    expect(screen.queryByText('Car Repairs')).not.toBeInTheDocument()
  })

  it('totals the overspent rows it lists, and puts the period beside them', () => {
    // The period's whole spend used to be the table's Total while "Overspent
    // only" was ticked. It is context now, with no share under a column of
    // variances.
    setQuery({
      data: {
        categories: [
          {
            category_id: 'c1',
            category_name: 'Groceries',
            category_group_name: 'Everyday',
            assigned: 500,
            spent: 450,
            variance: 50,
            variance_pct: 10,
            overspent: false,
          },
          {
            category_id: 'c2',
            category_name: 'Dining',
            category_group_name: 'Everyday',
            assigned: 100,
            spent: 160,
            variance: -60,
            variance_pct: -60,
            overspent: true,
          },
        ],
        total_assigned: '600',
        total_spent: '610',
      },
    })
    renderReport(<BudgetActualReport budgetId="b1" />)
    fireEvent.click(screen.getByLabelText('Overspent only'))

    expect(cellsOf('Total of the 1 shown')).toContain('$160.00')
    const whole = cellsOf('of $610.00 across 2 categories')
    expect(whole).toContain('$610.00')
    expect(whole.some((c) => c.includes('%'))).toBe(false)
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
        group_name: 'Bills',
        monthly_amounts: [700, 700],
        total: 1400,
        avg_monthly: 700,
        share: 77.78,
        category_ids: ['c1'],
      },
      {
        group_name: 'Fun',
        monthly_amounts: [200, 200],
        total: 400,
        avg_monthly: 200,
        share: 22.22,
        category_ids: ['c2'],
      },
    ],
    avg_monthly_cost_of_living: 900,
    avg_monthly_essentials: 700,
    avg_monthly_non_essential: 200,
    avg_monthly_income: 1200,
    required_ratio: 75,
    essentials_ratio: 58.33,
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
    expect(card('Essentials')).toEqual({ value: '$700.00', sub: 'could not be cut' })
    expect(card('Non-essential').value).toBe('$200.00')
    expect(card('Take-home')).toEqual({
      value: '$1,200.00',
      sub: 'per month, over 2 complete months',
    })
    expect(card('Required')).toEqual({ value: '75%', sub: 'of take-home' })
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
    expect(card('Non-essential').sub).toBe('22% of the above')
    expect(screen.queryByText(/could cut/i)).toBeNull()
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
      data: { ...tiered, required_ratio: 130, essentials_ratio: 108 },
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
        avg_monthly_non_essential: null,
        essentials_ratio: null,
        required_ratio: 130,
      },
    })
    renderReport(<CostOfLivingReport budgetId="b1" />)
    expect(screen.getByText('nothing tagged Essential')).toBeInTheDocument()
    expect(screen.getByText('needs Essentials tagged')).toBeInTheDocument()
    expect(screen.queryByText('could not be cut')).toBeNull()
    expect(screen.queryByText(/costs more than you take home/i)).toBeNull()
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

  it('Budget vs Actual', () => {
    setQuery({
      data: {
        categories: [
          {
            category_id: 'c1',
            category_name: 'Groceries',
            category_group_name: 'Everyday',
            assigned: 500,
            spent: 450,
            variance: 50,
            variance_pct: 10,
            overspent: false,
          },
        ],
        total_assigned: '500',
        total_spent: '450',
      },
    })
    renderReport(<BudgetActualReport budgetId="b1" />)
    noMinus('Groceries', '$450.00')
    noMinus('Total', '$450.00')
  })

  it('Income vs Expenses', () => {
    setQuery({
      data: {
        months: [
          {
            month: '2026-08-01',
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
    noMinus('2026-08', '$300.00')
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
        essentials_90d: 6.67,
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
        emergency_fund_balance: null,
        emergency_fund_source: null,
        runway_months: null,
        class_excluded: [],
      },
    })
    renderReport(<EssentialsReport budgetId="b1" />)
    const footer = screen.getByText('All essentials').closest('tr')
    expect(footer).toHaveTextContent('$20.00')
    expect(footer).not.toHaveTextContent('$20.01')
  })
})
