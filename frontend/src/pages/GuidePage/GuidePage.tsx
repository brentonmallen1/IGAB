import { useEffect } from 'react'
import { useGuideStore, GUIDE_TABS } from '../../stores/guideStore'
import { RoadmapPanel } from '../../components/guide/RoadmapPanel'
import { GlossaryPanel } from '../../components/guide/GlossaryPanel'
import { GuidePlaceholder } from '../../components/guide/GuidePlaceholder'
import './GuidePage.css'

/**
 * Guidance and tools — the roadmap, a financial checkup, scenario
 * calculators, a glossary and a wishlist.
 *
 * Shell-plus-tab-router, the same shape as ReportsPage. Nothing here reads the
 * user's data yet: the roadmap and glossary are content, and the three
 * remaining tabs describe what they will do rather than pretending to be
 * absent. Personalisation arrives with the signals work, behind a settings
 * toggle that is on by default.
 */
export function GuidePage() {
  const activeTab = useGuideStore((s) => s.activeTab)
  const setActiveTab = useGuideStore((s) => s.setActiveTab)

  // Guard against a persisted tab id that no longer exists — the same trap
  // ReportsPage hit when a tab was renamed.
  useEffect(() => {
    const valid = new Set(GUIDE_TABS.map((t) => t.id))
    if (!valid.has(activeTab)) setActiveTab('roadmap')
  }, [activeTab, setActiveTab])

  function renderTab() {
    switch (activeTab) {
      case 'roadmap':
        return <RoadmapPanel />
      case 'glossary':
        return <GlossaryPanel />
      case 'checkup':
        return (
          <GuidePlaceholder title="Financial checkup">
            <p>
              A short read of how things stand — savings rate, how many months your emergency
              fund covers, what you owe above 10%, and which categories you overspend month
              after month. Each one against a stated target, with a link to the roadmap step
              that addresses it.
            </p>
            <p>
              No single score: a number like “72/100” implies a precision that nothing here
              could honestly support. And IGAB will not notify you about any of it — the
              checkup is something you look at, plus a report you run when you want it.
            </p>
          </GuidePlaceholder>
        )
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
    <div className="guide-page">
      <nav className="guide-nav" aria-label="Guide navigation">
        <div className="guide-nav__tabs">
          {GUIDE_TABS.map((tab) => (
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
