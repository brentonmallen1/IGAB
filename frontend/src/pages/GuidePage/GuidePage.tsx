import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useGuideStore, GUIDE_TABS, type GuideTab } from '../../stores/guideStore'
import { TOOL_IDS, type ToolId } from '../../content/roadmap'
import { GLOSSARY_IDS, type GlossaryId } from '../../content/glossary'
import { useAppStore } from '../../stores/appStore'
import { useGuideOverview } from '../../api/guide'
import { RoadmapPanel } from '../../components/guide/RoadmapPanel'
import { GlossaryPanel } from '../../components/guide/GlossaryPanel'
import { CheckupPanel } from '../../components/guide/CheckupPanel'
import { ToolsPanel } from '../../components/guide/tools/ToolsPanel'
import './GuidePage.css'

/**
 * Guidance and tools — the roadmap, a financial checkup, scenario
 * calculators and a glossary. The wishlist lived here once; it is a working
 * tool rather than guidance, so it has a page of its own now, and old
 * `?tab=wishlist` links are walked over to it.
 *
 * Shell-plus-tab-router, the same shape as ReportsPage. The Checkup tab is
 * offered only while health reviews are on — off means the tab, the report
 * and the roadmap markers all go, not a tab that opens onto a notice.
 */
export function GuidePage() {
  const activeTab = useGuideStore((s) => s.activeTab)
  const setActiveTab = useGuideStore((s) => s.setActiveTab)
  const setActiveTool = useGuideStore((s) => s.setActiveTool)
  const setOpenGlossaryTerm = useGuideStore((s) => s.setOpenGlossaryTerm)
  const roadmapView = useGuideStore((s) => s.roadmapView)
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data: overview } = useGuideOverview(budgetId)
  // Optimistic while loading: both switches default on, so a flash of a
  // missing tab is the rarer wrong guess.
  const checkupOn = overview
    ? overview.preferences.personalization && overview.preferences.checkup
    : true
  const tabs = GUIDE_TABS.filter((t) => t.id !== 'checkup' || checkupOn)

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
  const navigate = useNavigate()
  useEffect(() => {
    const tab = searchParams.get('tab')
    const tool = searchParams.get('tool')
    const term = searchParams.get('term')
    if (!tab && !tool && !term) return
    // The wishlist's old address, honoured: it was a tab here for weeks.
    if (tab === 'wishlist') {
      navigate('/wishlist', { replace: true })
      return
    }
    if (tab && GUIDE_TABS.some((t) => t.id === tab)) setActiveTab(tab as GuideTab)
    if (tool && (TOOL_IDS as readonly string[]).includes(tool)) setActiveTool(tool as ToolId)
    // Validated against the id list exactly as ?tool= is: a term that no
    // longer exists must open the glossary, not a blank panel.
    if (term && (GLOSSARY_IDS as readonly string[]).includes(term)) {
      setOpenGlossaryTerm(term as GlossaryId)
    }
    setSearchParams({}, { replace: true })
  }, [navigate, searchParams, setActiveTab, setActiveTool, setOpenGlossaryTerm, setSearchParams])

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
