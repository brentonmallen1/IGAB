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

export interface ReportFilters {
  startDate: string
  endDate: string
  categoryIds: string[]
  payeeIds: string[]
  accountIds: string[]
  groupBy: GroupBy
}

export interface DrillDownContext {
  type: 'category' | 'category_group' | 'payee' | 'account'
  id: string
  name: string
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
      setFilters: (partial) => set((s) => ({ filters: { ...s.filters, ...partial } })),
      setDrillDown: (ctx) => set({ drillDown: ctx }),
      resetFilters: () => set({ filters: defaultFilters() }),
    }),
    {
      name: 'igab-reports',
      partialize: (s) => ({ activeTab: s.activeTab, filters: s.filters }),
    }
  )
)
