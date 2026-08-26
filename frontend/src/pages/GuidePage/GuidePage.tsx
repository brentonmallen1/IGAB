import { useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useGuideStore, GUIDE_TABS, type GuideTab } from '../../stores/guideStore'
import { TOOL_IDS, type ToolId } from '../../content/roadmap'
import { useAppStore } from '../../stores/appStore'
import { useGuideOverview } from '../../api/guide'
import { RoadmapPanel } from '../../components/guide/RoadmapPanel'
import { GlossaryPanel } from '../../components/guide/GlossaryPanel'
import { CheckupPanel } from '../../components/guide/CheckupPanel'
import { ToolsPanel } from '../../components/guide/tools/ToolsPanel'
import { WishlistPanel } from '../../components/guide/wishlist/WishlistPanel'
import './GuidePage.css'

/**
 * Guidance and tools — the roadmap, a financial checkup, scenario
 * calculators, a glossary and a wishlist.
 *
 * Shell-plus-tab-router, the same shape as ReportsPage. The Checkup tab is
 * offered only while health reviews are on — off means the tab, the report
 * and the roadmap markers all go, not a tab that opens onto a notice.
 */
export function GuidePage() {
  const activeTab = useGuideStore((s) => s.activeTab)
  const setActiveTab = useGuideStore((s) => s.setActiveTab)
  const setActiveTool = useGuideStore((s) => s.setActiveTool)
  const roadmapView = useGuideStore((s) => s.roadmapView)
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data: overview } = useGuideOverview(budgetId)
  // Optimistic while loading: both switches default on, so a flash of a
  // missing tab is the rarer wrong guess.
  const checkupOn = overview
    ? overview.preferences.personalization && overview.preferences.checkup
    : true
  const wishlistOn = overview ? overview.preferences.wishlist : true
  const tabs = GUIDE_TABS.filter(
    (t) => (t.id !== 'checkup' || checkupOn) && (t.id !== 'wishlist' || wishlistOn)
  )

  // The map pans and zooms inside its own viewport. If the page scrolled too,
  // one wheel gesture would drive both — which is exactly as confusing as it
  // sounds. Every other tab is an ordinary scrolling document.
  const fixedHeight = activeTab === 'roadmap' && roadmapView === 'map'

  // Guard against a persisted tab id that no longer exists — the same trap
  // ReportsPage hit when a tab was renamed — or one that is switched off.
  useEffect(() => {
    const valid = new Set(tabs.map((t) => t.id))
    if (!valid.has(activeTab)) setActiveTab('roadmap')
  }, [activeTab, setActiveTab, tabs])

  // A roadmap node can point at a tab and a calculator
  // (`/guide?tab=tools&tool=payoff-plan`). Read once, then the stored state
  // takes over — the same shape ReportsPage uses for `?tab=`.
  const [searchParams, setSearchParams] = useSearchParams()
  useEffect(() => {
    const tab = searchParams.get('tab')
    const tool = searchParams.get('tool')
    if (!tab && !tool) return
    if (tab && GUIDE_TABS.some((t) => t.id === tab)) setActiveTab(tab as GuideTab)
    if (tool && (TOOL_IDS as readonly string[]).includes(tool)) setActiveTool(tool as ToolId)
    setSearchParams({}, { replace: true })
  }, [searchParams, setActiveTab, setActiveTool, setSearchParams])

  function renderTab() {
    switch (activeTab) {
      case 'roadmap':
        return <RoadmapPanel />
      case 'glossary':
        return <GlossaryPanel />
      case 'checkup':
        return <CheckupPanel />
      case 'tools':
        return <ToolsPanel />
      case 'wishlist':
        return <WishlistPanel />
    }
  }

  return (
    <div className={`guide-page ${fixedHeight ? 'guide-page--fixed' : ''}`}>
      <nav className="guide-nav" aria-label="Guide navigation">
        <div className="guide-nav__tabs">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={`guide-nav__tab ${tab.id === activeTab ? 'guide-nav__tab--active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </nav>

      <main className="guide-content">{renderTab()}</main>
    </div>
  )
}
