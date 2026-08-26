import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { PERSIST_KEYS } from './persistKeys'

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
  | 'anomalies'
  | 'plan-reality'

export type TabGroup =
  | 'overview'
  | 'financial'
  | 'cashflow'
  | 'budget'
  | 'spending'
  | 'insights'

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
  { id: 'income-expense', label: 'Income vs Expenses', group: 'cashflow' },
  { id: 'burn-rate', label: 'Burn Rate', group: 'cashflow' },
  { id: 'cash-flow', label: 'Cash Flow', group: 'cashflow' },
  { id: 'projection', label: 'Projection', group: 'cashflow' },
  { id: 'budget-actual', label: 'Budget vs Actual', group: 'budget' },
  { id: 'variance', label: 'Cumulative Variance', group: 'budget' },
  { id: 'volatility', label: 'Volatility', group: 'budget' },
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
  'overview': { dates: true, categories: false, payees: false, accounts: false, groupBy: false },
  'net-worth': { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  'savings-rate': { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  'account-composition': { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  'liabilities': { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  'income-expense': { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  'burn-rate': { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  'cash-flow': { dates: true, categories: false, payees: false, accounts: true, groupBy: false },
  'projection': { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  'budget-actual': { dates: true, categories: true, payees: false, accounts: false, groupBy: false },
  'variance': { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  'volatility': { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  'pareto': { dates: true, categories: true, payees: true, accounts: true, groupBy: true, views: true },
  'treemap': { dates: true, categories: true, payees: false, accounts: true, groupBy: true, groupByModes: ['group', 'category'], views: true },
  'seasonality': { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  'subscriptions': { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  'savings': { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  'essentials': { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  'anomalies': { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  'plan-reality': { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  'payees': { dates: true, categories: false, payees: true, accounts: true, groupBy: false },
  'day-patterns': { dates: true, categories: true, payees: false, accounts: true, groupBy: false },
  'timeline': { dates: true, categories: true, payees: false, accounts: true, groupBy: false },
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
  categoryIds: string[]
  payeeIds: string[]
  accountIds: string[]
  groupBy: GroupBy
  /** Roll up by this view's arrangement. null = the budget's own groups. */
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
  dayOfWeek?: number
  /** Activity classes the originating chart counted. A chart that means
   *  "spending" must say so, or its drill lists savings and debt too — an
   *  $800 bar opening a panel that totals $1,800. */
  activityClasses?: string[]
  startDate: string
  endDate: string
}

interface ReportState {
  activeTab: ReportTab
  filters: ReportFilters
  drillDown: DrillDownContext | null

  setActiveTab: (tab: ReportTab) => void
  setFilters: (filters: Partial<ReportFilters>) => void
  setDrillDown: (ctx: DrillDownContext | null) => void
  resetFilters: () => void
}

function defaultFilters(): ReportFilters {
  const today = new Date()
  const start = new Date(today.getFullYear(), today.getMonth(), 1)
  return {
    startDate: start.toISOString().slice(0, 10),
    endDate: today.toISOString().slice(0, 10),
    categoryIds: [],
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
      drillDown: null,

      setActiveTab: (tab) => set({ activeTab: tab, drillDown: null }),
      // Filter changes invalidate the drill context (its window/ids were
      // resolved against the previous filters)
      setFilters: (partial) =>
        set((s) => ({ filters: { ...s.filters, ...partial }, drillDown: null })),
      setDrillDown: (ctx) => set({ drillDown: ctx }),
      resetFilters: () => set({ filters: defaultFilters(), drillDown: null }),
    }),
    {
      name: PERSIST_KEYS.reports,
      partialize: (s) => ({ activeTab: s.activeTab, filters: s.filters }),
    }
  )
)
