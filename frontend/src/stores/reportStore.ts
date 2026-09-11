import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { PERSIST_KEYS } from './persistKeys'
import { useMemo } from 'react'
import type { ReportScope } from '../api/reports'
import { thisMonthWindow } from '../utils/dateWindow'

export type ReportTab =
  | 'overview'
  | 'net-worth'
  | 'account-composition'
  | 'income-expense'
  | 'burn-rate'
  | 'cash-flow'
  | 'projection'
  | 'budget-actual'
  | 'variance'
  | 'volatility'
  | 'pareto'
  | 'treemap'
  | 'seasonality'
  | 'payees'
  | 'day-patterns'
  | 'timeline'
  | 'liabilities'
  | 'subscriptions'
  | 'savings'
  | 'savings-rate'
  | 'essentials'
  | 'emergency-fund'
  | 'anomalies'
  | 'plan-reality'
  | 'spending-trends'
  | 'spending-breakdown'
  | 'category-history'
  | 'income-sources'
  | 'cost-of-living'
  | 'wishlist'

export type TabGroup = 'overview' | 'financial' | 'cashflow' | 'budget' | 'spending' | 'insights'

export interface TabDef {
  id: ReportTab
  label: string
  group: TabGroup
}

export const REPORT_TABS: TabDef[] = [
  { id: 'overview', label: 'Overview', group: 'overview' },
  { id: 'net-worth', label: 'Net Worth', group: 'financial' },
  { id: 'account-composition', label: 'Accounts', group: 'financial' },
  { id: 'liabilities', label: 'Liabilities', group: 'financial' },
  { id: 'savings', label: 'Savings', group: 'financial' },
  { id: 'savings-rate', label: 'Savings Rate', group: 'financial' },
  { id: 'essentials', label: 'Essentials', group: 'financial' },
  { id: 'cost-of-living', label: 'Cost of Living', group: 'financial' },
  { id: 'emergency-fund', label: 'Emergency Fund', group: 'financial' },
  { id: 'income-expense', label: 'Income vs Expenses', group: 'cashflow' },
  { id: 'income-sources', label: 'Income by Source', group: 'cashflow' },
  { id: 'wishlist', label: 'Wishlist', group: 'spending' },
  { id: 'burn-rate', label: 'Burn Rate', group: 'cashflow' },
  { id: 'cash-flow', label: 'Cash Flow', group: 'cashflow' },
  { id: 'projection', label: 'Projection', group: 'cashflow' },
  { id: 'budget-actual', label: 'Budget vs Actual', group: 'budget' },
  { id: 'category-history', label: 'Category History', group: 'budget' },
  { id: 'variance', label: 'Cumulative Variance', group: 'budget' },
  { id: 'volatility', label: 'Volatility', group: 'budget' },
  { id: 'spending-trends', label: 'Spending Trends', group: 'spending' },
  { id: 'spending-breakdown', label: 'Breakdown', group: 'spending' },
  { id: 'pareto', label: 'Pareto', group: 'spending' },
  { id: 'treemap', label: 'Treemap', group: 'spending' },
  { id: 'seasonality', label: 'Seasonality', group: 'spending' },
  { id: 'subscriptions', label: 'Subscriptions', group: 'spending' },
  { id: 'plan-reality', label: 'Plan vs Reality', group: 'insights' },
  { id: 'anomalies', label: 'Anomalies', group: 'insights' },
  { id: 'payees', label: 'Payees', group: 'insights' },
  { id: 'day-patterns', label: 'Day Patterns', group: 'insights' },
  { id: 'timeline', label: 'Timeline', group: 'insights' },
]

export const TAB_GROUPS: { id: TabGroup; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'financial', label: 'Financial State' },
  { id: 'cashflow', label: 'Cash Flow' },
  { id: 'budget', label: 'Budget' },
  { id: 'spending', label: 'Spending' },
  { id: 'insights', label: 'Insights' },
]

/** Get the group a tab belongs to */
export function getTabGroup(tabId: ReportTab): TabGroup {
  const tab = REPORT_TABS.find((t) => t.id === tabId)
  return tab?.group ?? 'overview'
}

/** Get all tabs in a group */
export function getGroupTabs(groupId: TabGroup): TabDef[] {
  return REPORT_TABS.filter((t) => t.group === groupId)
}

export type GroupBy = 'group' | 'category' | 'payee'

/** Which activity classes a spending chart is counting, given its
 *  "Include savings & debt payments" toggle. Drill-downs pass this so the
 *  transaction list totals what the chart totals — the one list must never
 *  contradict the bar that opened it. Mirrors `_spending_classes` on the
 *  server; keep the two in step. */
export function spendingDrillClasses(includeSavings: boolean): string[] {
  return includeSavings ? ['spending', 'savings', 'debt_principal'] : ['spending']
}

/** The drill-down behind an Income figure: the rows every income figure
 *  counts, which is `INCOME_ROW` on the server — leaf rows of the income
 *  class. Parent rows are the wrong shape: a split paycheck of +1,000 pay and
 *  -300 fees is one +700 parent, so the Sankey's Income node, reading 1,000,
 *  opened a list totalling 700. One builder, because Income vs Expenses and
 *  the Sankey both open it. */
export function incomeDrill(
  label: string,
  window: { startDate: string; endDate: string }
): DrillDownContext {
  return {
    kind: 'month',
    label,
    scope: 'leaf',
    direction: 'inflow',
    activityClasses: ['income'],
    ...window,
  }
}

export interface TabFilterSupport {
  /** Whether the tab can roll up by a saved view's groups instead of the
   *  budget's own. Only the group-capable ones — everything else has no group
   *  dimension for a view to change. */
  views?: boolean
  dates: boolean
  categories: boolean
  payees: boolean
  accounts: boolean
  groupBy: boolean
  /** Which modes the tab can actually draw. Omitted = all three. The stored
   *  groupBy is shared across tabs, so a mode picked on one tab can be one
   *  another cannot draw — see resolveGroupBy. */
  groupByModes?: GroupBy[]
}

/** Which shared filters each report actually consumes — the filter bar dims
 * the rest so filters never silently appear to apply. Months-based reports
 * (their own 6/12/24mo selector) ignore the date range too. */
export const TAB_FILTER_SUPPORT: Record<ReportTab, TabFilterSupport> = {
  overview: { dates: true, categories: false, payees: false, accounts: false, groupBy: false },
  'net-worth': { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  'savings-rate': {
    dates: false,
    categories: false,
    payees: false,
    accounts: false,
    groupBy: false,
  },
  'account-composition': {
    dates: false,
    categories: false,
    payees: false,
    accounts: false,
    groupBy: false,
  },
  liabilities: { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  'income-expense': {
    dates: false,
    categories: false,
    payees: false,
    accounts: false,
    groupBy: false,
  },
  'burn-rate': { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  'cash-flow': { dates: true, categories: false, payees: false, accounts: true, groupBy: false },
  projection: { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  'budget-actual': {
    dates: true,
    categories: true,
    payees: false,
    accounts: false,
    groupBy: false,
  },
  variance: { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  volatility: { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  pareto: {
    dates: true,
    categories: true,
    payees: true,
    accounts: true,
    groupBy: true,
    views: true,
  },
  treemap: {
    dates: true,
    categories: true,
    payees: false,
    accounts: true,
    groupBy: true,
    groupByModes: ['group', 'category'],
    views: true,
  },
  seasonality: { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  subscriptions: {
    dates: false,
    categories: false,
    payees: false,
    accounts: false,
    groupBy: false,
  },
  savings: { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  essentials: { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  // Its own months selector, like Essentials — and its scope is the Essential
  // tag and the Guide's emergency-fund binding, neither of which the shared
  // category/payee/account filters can narrow without making the coverage
  // figure mean something else.
  'emergency-fund': {
    dates: false,
    categories: false,
    payees: false,
    accounts: false,
    groupBy: false,
  },
  anomalies: { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  'plan-reality': {
    dates: false,
    categories: false,
    payees: false,
    accounts: false,
    groupBy: false,
  },
  payees: { dates: true, categories: false, payees: true, accounts: true, groupBy: false },
  'spending-trends': {
    dates: true,
    categories: true,
    payees: false,
    accounts: true,
    groupBy: true,
    groupByModes: ['group', 'category'],
  },
  'spending-breakdown': {
    dates: true,
    categories: true,
    payees: false,
    accounts: true,
    groupBy: false,
    views: true,
  },
  'category-history': {
    dates: false,
    categories: false,
    payees: false,
    accounts: false,
    groupBy: false,
  },
  'income-sources': {
    dates: false,
    categories: false,
    payees: false,
    accounts: false,
    groupBy: false,
  },
  // Both drive their own window (or none at all), so the shared filter bar
  // has nothing to offer either.
  'cost-of-living': {
    dates: false,
    categories: false,
    payees: false,
    accounts: false,
    groupBy: false,
  },
  wishlist: { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  'day-patterns': { dates: true, categories: true, payees: false, accounts: true, groupBy: false },
  timeline: { dates: true, categories: true, payees: false, accounts: true, groupBy: false },
}

/** The mode a tab actually draws for the stored preference.

Tabs share one stored groupBy, so "Payee" picked on the pareto arrives at
the treemap, which has no payee data. Before this resolver the treemap
silently drew group tiles under a highlighted Payee button — group names
where the user asked for payees. Fall back to the tab's first mode, and
never write the fallback to the store: the preference should survive the
detour and still mean payee when the user returns to a tab that can draw it. */
export function resolveGroupBy(tab: ReportTab, groupBy: GroupBy): GroupBy {
  const support = TAB_FILTER_SUPPORT[tab]
  const modes = support.groupByModes
  if (!support.groupBy || !modes || modes.includes(groupBy)) return groupBy
  return modes[0]
}

export interface ReportFilters {
  startDate: string
  endDate: string
  /** The three ways of saying which categories a report is about. They UNION
   *  on the server (`services/report_scope.py`): each one adds to the scope,
   *  because three controls side by side read as "and also this", and
   *  narrowing twice by accident is a worse surprise than widening. */
  categoryIds: string[]
  /** Categories carrying any of these tags join the scope. Dynamic by nature —
   *  no saved row, so tagging a category later widens the report with nothing
   *  to keep in step. */
  tagIds: string[]
  /** A saved filter's effective set: its named categories plus everything
   *  carrying its tags, resolved server-side by the same call the budget page
   *  makes. null = none chosen. */
  filterId: string | null
  payeeIds: string[]
  accountIds: string[]
  groupBy: GroupBy
  /** Roll up by this view's arrangement. null = the budget's own groups.
   *  Deliberately NOT part of the scope above: a view is an arrangement and a
   *  scope is a predicate, and both can be on at once. */
  viewId: string | null
}

/** Fully-resolved drill-down request; charts resolve ids and the date window
 * at click time so the panel needs no chart-specific knowledge. */
export interface DrillDownContext {
  kind: 'category' | 'category-group' | 'payee' | 'month' | 'day-of-week'
  label: string
  /** leaf = category-keyed charts (split children as rows); parent = payee/month charts */
  scope: 'leaf' | 'parent'
  direction?: 'outflow' | 'inflow'
  categoryIds?: string[]
  payeeIds?: string[]
  /** The other two scope axes, for a drill opened from a chart that had no
   *  category ids of its own — see `components/reports/drillScope.ts` for why
   *  a chart WITH its own ids must not send these. */
  tagIds?: string[]
  filterId?: string | null
  /** Rows with no category, for a bucket that is defined by their absence
   *  (served as `no_category`). An empty `categoryIds` cannot say this — it
   *  filters nothing and lists the whole window, which is worse than not
   *  offering the drill at all. Not the register's Uncategorized filter: that
   *  is the needs-a-category rule, which leaves out rows before an account's
   *  budget start and rows on tracking accounts that a report bucket counted. */
  noCategory?: boolean
  dayOfWeek?: number
  /** Activity classes the originating chart counted. A chart that means
   *  "spending" must say so, or its drill lists savings and debt too — an
   *  $800 bar opening a panel that totals $1,800. */
  activityClasses?: string[]
  /** A necessity tier the chart rolled up (served as `necessity_tier`). Its
   *  membership is per row — debt principal by class — so categories and
   *  classes alone list rows the bar never counted. */
  necessityTier?: string
  startDate: string
  endDate: string
}

/** The window a month-based report opens on before anyone has chosen one. */
export const DEFAULT_RANGE_MONTHS = 12

interface ReportState {
  activeTab: ReportTab
  filters: ReportFilters
  /** How many months the month-windowed reports show.
   *
   *  Sixteen reports each held this in `useState(12)`, and the tabs are
   *  separate components — so switching report unmounted the one holding the
   *  choice and the next one initialised its own copy. Picking 6 months and
   *  finding 12 again one tab later is not a preference being ignored, it is
   *  sixteen preferences that never knew about each other.
   *
   *  It sits beside `filters` rather than inside it because it is not part of
   *  the scope the server resolves: the reports that take it turn it into
   *  their own window, and the ones that do not (`TAB_FILTER_SUPPORT.dates`)
   *  never see it. */
  rangeMonths: number
  /** Whether the nav is showing the starred reports rather than a group.
   *
   *  A stored flag rather than a seventh `TabGroup`, because a starred report
   *  keeps its real group — the row has to survive picking a report that
   *  belongs to Spending without flipping the nav to Spending. It holds only
   *  while the active tab is actually starred (`reportNav`), so unstarring
   *  the one you are on needs no separate cleanup. */
  navFavorites: boolean
  drillDown: DrillDownContext | null

  setActiveTab: (tab: ReportTab) => void
  setRangeMonths: (months: number) => void
  setNavFavorites: (on: boolean) => void
  setFilters: (filters: Partial<ReportFilters>) => void
  setDrillDown: (ctx: DrillDownContext | null) => void
  resetFilters: () => void
}

function defaultFilters(): ReportFilters {
  const { start, end } = thisMonthWindow()
  return {
    startDate: start,
    endDate: end,
    categoryIds: [],
    tagIds: [],
    filterId: null,
    payeeIds: [],
    accountIds: [],
    groupBy: 'category',
    viewId: null,
  }
}

export const useReportStore = create<ReportState>()(
  persist(
    (set) => ({
      activeTab: 'overview',
      filters: defaultFilters(),
      rangeMonths: DEFAULT_RANGE_MONTHS,
      navFavorites: false,
      drillDown: null,

      setActiveTab: (tab) => set({ activeTab: tab, drillDown: null }),
      // Clears the drill for the same reason a filter change does: the open
      // panel's window was resolved against the window that just moved.
      setRangeMonths: (months) => set({ rangeMonths: months, drillDown: null }),
      setNavFavorites: (on) => set({ navFavorites: on }),
      // Filter changes invalidate the drill context (its window/ids were
      // resolved against the previous filters)
      setFilters: (partial) =>
        set((s) => ({ filters: { ...s.filters, ...partial }, drillDown: null })),
      setDrillDown: (ctx) => set({ drillDown: ctx }),
      resetFilters: () => set({ filters: defaultFilters(), drillDown: null }),
    }),
    {
      name: PERSIST_KEYS.reports,
      partialize: (s) => ({
        activeTab: s.activeTab,
        filters: s.filters,
        rangeMonths: s.rangeMonths,
        navFavorites: s.navFavorites,
      }),
      // A state persisted before a filter field existed arrives without it,
      // and `filters.tagIds.length` on undefined is a blank Reports page for
      // anyone who used the tab before upgrading. Filling from the defaults
      // says that once, for every field added since — cheaper and safer than
      // a version bump per field, and it cannot forget one.
      merge: (persisted, current) => {
        const saved = (persisted ?? {}) as Partial<ReportState>
        return {
          ...current,
          ...saved,
          filters: { ...defaultFilters(), ...(saved.filters ?? {}) },
        }
      },
    }
  )
)

/**
 * The scope the filter bar has set, in the shape every report hook takes.
 *
 * One reader, so a chart cannot pass two of the three axes and quietly widen
 * its own report — and so a fourth axis added later reaches every chart at
 * once instead of the ones someone remembered. Memoised on the three fields,
 * because the object is part of each query's cache key and a fresh identity
 * every render would refetch on every render.
 */
export function useReportScope(): ReportScope {
  const { categoryIds, tagIds, filterId } = useReportStore((s) => s.filters)
  return useMemo(() => ({ categoryIds, tagIds, filterId }), [categoryIds, tagIds, filterId])
}

/**
 * The shared month window a report draws.
 *
 * Read-only on purpose: `ReportRangeSelect` is the only thing that sets it,
 * and every report renders that control rather than wiring its own. Sixteen
 * of them used to own a `useState(12)` and hand it down, which is exactly how
 * the window came to mean something different on each tab.
 */
export function useReportMonths(): number {
  return useReportStore((s) => s.rangeMonths)
}
