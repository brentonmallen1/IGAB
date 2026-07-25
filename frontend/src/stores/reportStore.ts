import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type ReportTab =
  | 'overview'
  | 'net-worth'
  | 'account-composition'
  | 'income-expense'
  | 'burn-rate'
  | 'cash-flow'
  | 'budget-actual'
  | 'variance'
  | 'volatility'
  | 'pareto'
  | 'treemap'
  | 'seasonality'
  | 'payees'
  | 'day-patterns'
  | 'timeline'

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
  { id: 'income-expense', label: 'Income vs Expenses', group: 'cashflow' },
  { id: 'burn-rate', label: 'Burn Rate', group: 'cashflow' },
  { id: 'cash-flow', label: 'Cash Flow', group: 'cashflow' },
  { id: 'budget-actual', label: 'Budget vs Actual', group: 'budget' },
  { id: 'variance', label: 'Cumulative Variance', group: 'budget' },
  { id: 'volatility', label: 'Volatility', group: 'budget' },
  { id: 'pareto', label: 'Pareto', group: 'spending' },
  { id: 'treemap', label: 'Treemap', group: 'spending' },
  { id: 'seasonality', label: 'Seasonality', group: 'spending' },
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

export type GroupBy = 'group' | 'category' | 'payee'

export interface TabFilterSupport {
  dates: boolean
  categories: boolean
  payees: boolean
  accounts: boolean
  groupBy: boolean
}

/** Which shared filters each report actually consumes — the filter bar dims
 * the rest so filters never silently appear to apply. Months-based reports
 * (their own 6/12/24mo selector) ignore the date range too. */
export const TAB_FILTER_SUPPORT: Record<ReportTab, TabFilterSupport> = {
  'overview': { dates: true, categories: false, payees: false, accounts: false, groupBy: false },
  'net-worth': { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  'account-composition': { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  'income-expense': { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  'burn-rate': { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  'cash-flow': { dates: true, categories: false, payees: false, accounts: true, groupBy: false },
  'budget-actual': { dates: true, categories: true, payees: false, accounts: false, groupBy: false },
  'variance': { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  'volatility': { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  'pareto': { dates: true, categories: true, payees: true, accounts: true, groupBy: true },
  'treemap': { dates: true, categories: true, payees: false, accounts: true, groupBy: true },
  'seasonality': { dates: false, categories: false, payees: false, accounts: false, groupBy: false },
  'payees': { dates: true, categories: false, payees: true, accounts: true, groupBy: false },
  'day-patterns': { dates: true, categories: true, payees: false, accounts: true, groupBy: false },
  'timeline': { dates: true, categories: true, payees: false, accounts: true, groupBy: false },
}

export interface ReportFilters {
  startDate: string
  endDate: string
  categoryIds: string[]
  payeeIds: string[]
  accountIds: string[]
  groupBy: GroupBy
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
      name: 'igab-reports',
      partialize: (s) => ({ activeTab: s.activeTab, filters: s.filters }),
    }
  )
)
