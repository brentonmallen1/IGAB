import { useAppStore } from '../../stores/appStore'
import {
  useReportStore,
  REPORT_TABS,
  TAB_GROUPS,
  type ReportTab,
  type TabGroup,
} from '../../stores/reportStore'
import { ReportFiltersBar } from '../../components/reports/ReportFilters/ReportFiltersBar'
import { DrillDownPanel } from '../../components/reports/DrillDownPanel/DrillDownPanel'
import { OverviewReport } from '../../components/reports/OverviewReport'
import { NetWorthReport } from '../../components/reports/charts/NetWorthChart'
import { AccountCompositionReport } from '../../components/reports/charts/AccountCompositionChart'
import { IncomeExpenseReport } from '../../components/reports/charts/IncomeExpenseChart'
import { BurnRateReport } from '../../components/reports/charts/BurnRateChart'
import { CashFlowSankeyReport } from '../../components/reports/charts/CashFlowSankey'
import { BudgetActualReport } from '../../components/reports/charts/BudgetActualChart'
import { VarianceReport } from '../../components/reports/charts/VarianceChart'
import { VolatilityReport } from '../../components/reports/charts/VolatilityChart'
import { ParetoReport } from '../../components/reports/charts/ParetoChart'
import { SpendingTreemapReport } from '../../components/reports/charts/SpendingTreemap'
import { SeasonalityReport } from '../../components/reports/charts/SeasonalityHeatmap'
import { PayeeReport } from '../../components/reports/charts/PayeeChart'
import { DayPatternsReport } from '../../components/reports/charts/DayOfWeekChart'
import { TimelineReport } from '../../components/reports/charts/EventTimeline'
import { LiabilitiesReport } from '../../components/reports/charts/LiabilitiesReport'
import { useEffect } from 'react'
import './ReportsPage.css'

const GROUP_LABELS: Record<TabGroup, string> = {
  overview: 'Overview',
  financial: 'Financial State',
  cashflow: 'Cash Flow',
  budget: 'Budget',
  spending: 'Spending',
  insights: 'Insights',
}

export function ReportsPage() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { activeTab, setActiveTab } = useReportStore()

  // Guard against stale persisted tab ids (e.g. 'debts' was renamed to 'liabilities')
  useEffect(() => {
    const validIds = new Set(REPORT_TABS.map((t) => t.id))
    if (!validIds.has(activeTab)) {
      setActiveTab('overview')
    }
  }, [activeTab, setActiveTab])

  if (!budgetId) {
    return (
      <div className="reports-page">
        <div className="reports-empty">Select a budget to view reports.</div>
      </div>
    )
  }

  function renderReport() {
    switch (activeTab) {
      case 'overview': return <OverviewReport budgetId={budgetId!} />
      case 'net-worth': return <NetWorthReport budgetId={budgetId!} />
      case 'account-composition': return <AccountCompositionReport budgetId={budgetId!} />
      case 'liabilities': return <LiabilitiesReport budgetId={budgetId!} />
      case 'income-expense': return <IncomeExpenseReport budgetId={budgetId!} />
      case 'burn-rate': return <BurnRateReport budgetId={budgetId!} />
      case 'cash-flow': return <CashFlowSankeyReport budgetId={budgetId!} />
      case 'budget-actual': return <BudgetActualReport budgetId={budgetId!} />
      case 'variance': return <VarianceReport budgetId={budgetId!} />
      case 'volatility': return <VolatilityReport budgetId={budgetId!} />
      case 'pareto': return <ParetoReport budgetId={budgetId!} />
      case 'treemap': return <SpendingTreemapReport budgetId={budgetId!} />
      case 'seasonality': return <SeasonalityReport budgetId={budgetId!} />
      case 'payees': return <PayeeReport budgetId={budgetId!} />
      case 'day-patterns': return <DayPatternsReport budgetId={budgetId!} />
      case 'timeline': return <TimelineReport budgetId={budgetId!} />
    }
  }

  const tabsByGroup = REPORT_TABS.reduce<Partial<Record<TabGroup, typeof REPORT_TABS>>>((acc, tab) => {
    if (!acc[tab.group]) acc[tab.group] = []
    acc[tab.group]!.push(tab)
    return acc
  }, {})

  return (
    <div className="reports-page">
      <nav className="reports-nav" aria-label="Report navigation">
        <div className="reports-nav__groups">
          {TAB_GROUPS.map((group) => {
            const tabs = tabsByGroup[group.id] ?? []
            const isGroupActive = tabs.some((t) => t.id === activeTab)
            return (
              <div key={group.id} className={`reports-nav__group ${isGroupActive ? 'reports-nav__group--active' : ''}`}>
                <div className="reports-nav__group-label" onClick={() => setActiveTab(tabs[0].id as ReportTab)}>
                  {GROUP_LABELS[group.id]}
                </div>
                <div className="reports-nav__group-tabs">
                  {tabs.map((tab) => (
                    <button
                      key={tab.id}
                      className={`reports-nav__tab ${tab.id === activeTab ? 'reports-nav__tab--active' : ''}`}
                      onClick={() => setActiveTab(tab.id)}
                      type="button"
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </nav>

      <ReportFiltersBar budgetId={budgetId} />

      <main className="reports-content">
        {renderReport()}
        <DrillDownPanel budgetId={budgetId} />
      </main>
    </div>
  )
}
