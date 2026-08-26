import { useEffect } from 'react'
import { useGuideStore, GUIDE_TABS } from '../../stores/guideStore'
import { useAppStore } from '../../stores/appStore'
import { useGuideOverview } from '../../api/guide'
import { RoadmapPanel } from '../../components/guide/RoadmapPanel'
import { GlossaryPanel } from '../../components/guide/GlossaryPanel'
import { CheckupPanel } from '../../components/guide/CheckupPanel'
import { GuidePlaceholder } from '../../components/guide/GuidePlaceholder'
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

  function renderTab() {
    switch (activeTab) {
      case 'roadmap':
        return <RoadmapPanel />
      case 'glossary':
        return <GlossaryPanel />
      case 'checkup':
        return <CheckupPanel />
      case 'tools':
        return (
          <GuidePlaceholder title="Scenario tools">
            <p>
              Calculators for the questions the roadmap raises. Avalanche against snowball
              with your real debts, including what happens when a cleared debt frees up its
              payment. Whether to pay a debt down or save the money instead. Which of two
              loans costs less. How large an emergency fund actually needs to be.
            </p>
            <p>
              These will only ever show arithmetic that can be shown its working — no
              projected market returns, no tax modelling, no advice.
            </p>
          </GuidePlaceholder>
        )
      case 'wishlist':
        return (
          <GuidePlaceholder title="Wishlist">
            <p>
              Not a shopping list — the counterweight to one. Somewhere to park something you
              want, attach it to a real category, and let time and funding decide whether it
              still matters. The friction is the point: an impulse that survives three months
              of sitting on a list was never an impulse.
            </p>
            <p>
              It turns a fun budget into a purposeful one. You will see what you can afford
              now, roughly how long the rest would take at your current rate of saving, and
              which items you added a while ago and still want.
            </p>
          </GuidePlaceholder>
        )
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
