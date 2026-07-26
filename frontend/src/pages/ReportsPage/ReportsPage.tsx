import { useAppStore } from '../../stores/appStore'
import {
  useReportStore,
  REPORT_TABS,
  TAB_GROUPS,
  getTabGroup,
  getGroupTabs,
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
import { ChevronDown } from 'lucide-react'
import { useEffect, useState, useRef } from 'react'
import './ReportsPage.css'

export function ReportsPage() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { activeTab, setActiveTab } = useReportStore()
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Derive active group from active tab
  const activeGroup = getTabGroup(activeTab)
  const groupTabs = getGroupTabs(activeGroup)
  const activeGroupLabel = TAB_GROUPS.find((g) => g.id === activeGroup)?.label ?? 'Reports'

  // Guard against stale persisted tab ids (e.g. 'debts' was renamed to 'liabilities')
  useEffect(() => {
    const validIds = new Set(REPORT_TABS.map((t) => t.id))
    if (!validIds.has(activeTab)) {
      setActiveTab('overview')
    }
  }, [activeTab, setActiveTab])

  // Close dropdown on click outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false)
      }
    }
    if (dropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [dropdownOpen])

  // Close dropdown on escape
  useEffect(() => {
    function handleEscape(e: KeyboardEvent) {
      if (e.key === 'Escape') setDropdownOpen(false)
    }
    if (dropdownOpen) {
      document.addEventListener('keydown', handleEscape)
      return () => document.removeEventListener('keydown', handleEscape)
    }
  }, [dropdownOpen])

  function handleGroupSelect(groupId: TabGroup) {
    const firstTab = getGroupTabs(groupId)[0]
    if (firstTab) setActiveTab(firstTab.id)
    setDropdownOpen(false)
  }

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

  return (
    <div className="reports-page">
      <nav className="reports-nav" aria-label="Report navigation">
        <div className="reports-nav__row">
          {/* Group dropdown */}
          <div className="reports-nav__dropdown" ref={dropdownRef}>
            <button
              className="reports-nav__dropdown-trigger"
              onClick={() => setDropdownOpen(!dropdownOpen)}
              aria-expanded={dropdownOpen}
              aria-haspopup="listbox"
              type="button"
            >
              <span>{activeGroupLabel}</span>
              <ChevronDown size={16} className={`reports-nav__dropdown-icon ${dropdownOpen ? 'reports-nav__dropdown-icon--open' : ''}`} />
            </button>
            {dropdownOpen && (
              <ul className="reports-nav__dropdown-menu" role="listbox">
                {TAB_GROUPS.map((group) => (
                  <li
                    key={group.id}
                    role="option"
                    aria-selected={group.id === activeGroup}
                    className={`reports-nav__dropdown-item ${group.id === activeGroup ? 'reports-nav__dropdown-item--active' : ''}`}
                    onClick={() => handleGroupSelect(group.id)}
                  >
                    {group.label}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="reports-nav__separator" />

          {/* Horizontal tabs for the current group */}
          <div className="reports-nav__tabs">
            {groupTabs.map((tab) => (
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
      </nav>

      <ReportFiltersBar budgetId={budgetId} />

      <main className="reports-content">
        {renderReport()}
        <DrillDownPanel budgetId={budgetId} />
      </main>
    </div>
  )
}
