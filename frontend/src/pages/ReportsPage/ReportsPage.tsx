import { useSearchParams } from 'react-router-dom'
import { useAppStore } from '../../stores/appStore'
import {
  useReportStore,
  REPORT_TABS,
  TAB_GROUPS,
  getTabGroup,
  getGroupTabs,
  type ReportTab,
  type TabGroup,
} from '../../stores/reportStore'
import { ReportFiltersBar } from '../../components/reports/ReportFilters/ReportFiltersBar'
import { ReportsMobileChrome } from '../../components/reports/ReportsMobileChrome'
import { PageHeader } from '../../components/common/PageHeader/PageHeader'
import { useIsMobile } from '../../hooks/useMediaQuery'
import { DrillDownPanel } from '../../components/reports/DrillDownPanel/DrillDownPanel'
import { OverviewReport } from '../../components/reports/OverviewReport'
import { EssentialsReport } from '../../components/reports/charts/EssentialsReport'
import { EmergencyCoverageReport } from '../../components/reports/charts/EmergencyCoverageReport'
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
import { SubscriptionsReport } from '../../components/reports/charts/SubscriptionsReport'
import { SavingsReport } from '../../components/reports/charts/SavingsReport'
import { SavingsRateReport } from '../../components/reports/charts/SavingsRateChart'
import { AnomaliesReport } from '../../components/reports/charts/AnomaliesReport'
import { PlanVsRealityReport } from '../../components/reports/charts/PlanVsRealityReport'
import { CashProjectionReport } from '../../components/reports/charts/CashProjectionReport'
import { SpendingTrendsReport } from '../../components/reports/charts/SpendingTrendsReport'
import { SpendingBreakdownReport } from '../../components/reports/charts/SpendingBreakdownReport'
import { CategoryHistoryReport } from '../../components/reports/charts/CategoryHistoryReport'
import { CostOfLivingReport } from '../../components/reports/charts/CostOfLivingReport'
import { WishlistDisciplineReport } from '../../components/reports/charts/WishlistDisciplineReport'
import { IncomeSourcesReport } from '../../components/reports/charts/IncomeSourcesReport'
import { ChevronDown, Star } from 'lucide-react'
import { useEffect, useState, useRef } from 'react'
import './ReportsPage.css'
import { Surface } from '../../components/common/Surface'
import { useReportFavorites, useSetReportFavorites } from '../../api/reportFavorites'
import { FAVORITES_LABEL, reportNav, toggleFavorite } from './reportNav'

export function ReportsPage() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { activeTab, setActiveTab } = useReportStore()
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const navFavorites = useReportStore((s) => s.navFavorites)
  const setNavFavorites = useReportStore((s) => s.setNavFavorites)
  const { data: favorites } = useReportFavorites(budgetId)
  const setFavorites = useSetReportFavorites(budgetId)
  const isMobile = useIsMobile()

  // Which row of reports to draw, and what the dropdown reads. `reportNav`
  // owns the rule that a starred report keeps its real group — see there.
  const starred = favorites ?? []
  const nav = reportNav(activeTab, navFavorites, starred)
  const activeGroup = getTabGroup(activeTab)
  const isStarred = starred.includes(activeTab)

  // Guard against stale persisted tab ids (e.g. 'debts' was renamed to 'liabilities')
  useEffect(() => {
    const validIds = new Set(REPORT_TABS.map((t) => t.id))
    if (!validIds.has(activeTab)) {
      setActiveTab('overview')
    }
  }, [activeTab, setActiveTab])

  // A link can name a tab (`/reports?tab=essentials`) — the Guide's roadmap
  // points at specific reports. Read once, then the stored tab takes over.
  const [searchParams, setSearchParams] = useSearchParams()
  useEffect(() => {
    const wanted = searchParams.get('tab')
    if (!wanted) return
    if (REPORT_TABS.some((t) => t.id === wanted)) setActiveTab(wanted as ReportTab)
    setSearchParams({}, { replace: true })
  }, [searchParams, setActiveTab, setSearchParams])

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
    setNavFavorites(false)
    setDropdownOpen(false)
  }

  function handleFavoritesSelect() {
    setNavFavorites(true)
    // Only jump if the report on screen is not already starred: arriving at
    // the starred row should not move you off the report you were reading.
    if (!starred.includes(activeTab) && starred[0]) setActiveTab(starred[0])
    setDropdownOpen(false)
  }

  function handleToggleStar() {
    setFavorites.mutate(toggleFavorite(starred, activeTab))
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
      case 'overview':
        return <OverviewReport budgetId={budgetId!} />
      case 'net-worth':
        return <NetWorthReport budgetId={budgetId!} />
      case 'account-composition':
        return <AccountCompositionReport budgetId={budgetId!} />
      case 'liabilities':
        return <LiabilitiesReport budgetId={budgetId!} />
      case 'savings':
        return <SavingsReport budgetId={budgetId!} />
      case 'savings-rate':
        return <SavingsRateReport budgetId={budgetId!} />
      case 'essentials':
        return <EssentialsReport budgetId={budgetId!} />
      case 'emergency-fund':
        return <EmergencyCoverageReport budgetId={budgetId!} />
      case 'income-expense':
        return <IncomeExpenseReport budgetId={budgetId!} />
      case 'burn-rate':
        return <BurnRateReport budgetId={budgetId!} />
      case 'cash-flow':
        return <CashFlowSankeyReport budgetId={budgetId!} />
      case 'projection':
        return <CashProjectionReport budgetId={budgetId!} />
      case 'budget-actual':
        return <BudgetActualReport budgetId={budgetId!} />
      case 'variance':
        return <VarianceReport budgetId={budgetId!} />
      case 'volatility':
        return <VolatilityReport budgetId={budgetId!} />
      case 'pareto':
        return <ParetoReport budgetId={budgetId!} />
      case 'treemap':
        return <SpendingTreemapReport budgetId={budgetId!} />
      case 'seasonality':
        return <SeasonalityReport budgetId={budgetId!} />
      case 'subscriptions':
        return <SubscriptionsReport budgetId={budgetId!} />
      case 'plan-reality':
        return <PlanVsRealityReport budgetId={budgetId!} />
      case 'anomalies':
        return <AnomaliesReport budgetId={budgetId!} />
      case 'payees':
        return <PayeeReport budgetId={budgetId!} />
      case 'day-patterns':
        return <DayPatternsReport budgetId={budgetId!} />
      case 'timeline':
        return <TimelineReport budgetId={budgetId!} />
      case 'spending-trends':
        return <SpendingTrendsReport budgetId={budgetId!} />
      case 'spending-breakdown':
        return <SpendingBreakdownReport budgetId={budgetId!} />
      case 'category-history':
        return <CategoryHistoryReport budgetId={budgetId!} />
      case 'income-sources':
        return <IncomeSourcesReport budgetId={budgetId!} />
      case 'cost-of-living':
        return <CostOfLivingReport budgetId={budgetId!} />
      case 'wishlist':
        return <WishlistDisciplineReport budgetId={budgetId!} />
    }
  }

  if (isMobile) {
    // One row of chrome instead of up to seven bands — see ReportsMobileChrome.
    return (
      <div className="reports-page">
        <PageHeader title="Reports" />
        <ReportsMobileChrome
          budgetId={budgetId}
          starred={starred}
          onToggleStar={handleToggleStar}
          starPending={setFavorites.isPending}
        />
        <main className="reports-content">
          {renderReport()}
          <DrillDownPanel budgetId={budgetId} />
        </main>
      </div>
    )
  }

  return (
    <div className="reports-page">
      <Surface as="nav" variant="chrome" className="reports-nav" aria-label="Report navigation">
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
              <span>{nav.label}</span>
              <ChevronDown
                size={16}
                className={`reports-nav__dropdown-icon ${dropdownOpen ? 'reports-nav__dropdown-icon--open' : ''}`}
              />
            </button>
            {dropdownOpen && (
              <ul className="reports-nav__dropdown-menu" role="listbox">
                {/* Only once something is starred — an empty row would be a
                    dead end, and the star that fills it is on this same bar. */}
                {starred.length > 0 && (
                  <li
                    role="option"
                    aria-selected={nav.favorites}
                    className={`reports-nav__dropdown-item reports-nav__dropdown-item--favorites ${nav.favorites ? 'reports-nav__dropdown-item--active' : ''}`}
                    onClick={handleFavoritesSelect}
                  >
                    <Star size={13} aria-hidden="true" />
                    {FAVORITES_LABEL}
                  </li>
                )}
                {TAB_GROUPS.map((group) => (
                  <li
                    key={group.id}
                    role="option"
                    aria-selected={!nav.favorites && group.id === activeGroup}
                    className={`reports-nav__dropdown-item ${!nav.favorites && group.id === activeGroup ? 'reports-nav__dropdown-item--active' : ''}`}
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
            {nav.tabs.map((tab) => (
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

          {/* Stars the report you are reading, which is when you know you
              want it back. Outside the scrolling tab row so it stays put. */}
          <button
            type="button"
            className={`reports-nav__star ${isStarred ? 'reports-nav__star--on' : ''}`}
            onClick={handleToggleStar}
            disabled={setFavorites.isPending}
            aria-pressed={isStarred}
            title={isStarred ? 'Remove from favorites' : 'Add to favorites'}
            aria-label={isStarred ? 'Remove from favorites' : 'Add to favorites'}
          >
            <Star size={15} fill={isStarred ? 'currentColor' : 'none'} />
          </button>
        </div>
      </Surface>

      <ReportFiltersBar budgetId={budgetId} />

      <main className="reports-content">
        {renderReport()}
        <DrillDownPanel budgetId={budgetId} />
      </main>
    </div>
  )
}
