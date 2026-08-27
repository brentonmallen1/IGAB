import { useState } from 'react'
import { ExternalLink, Info } from 'lucide-react'
import {
  ROADMAP_STEPS,
  ROADMAP_ATTRIBUTION,
  ROADMAP_DISCLAIMER,
} from '../../content/roadmap'
import { useGuideStore, type RoadmapView } from '../../stores/guideStore'
import { stepColor } from './stepColor'
import { GuideDialog } from './GuideDialog'
import { RoadmapJourney } from './RoadmapJourney'
import { RoadmapBrowse } from './RoadmapBrowse'
import { RoadmapMap } from './RoadmapMap'
import { PositionStrip } from './PositionStrip'

const VIEWS: { id: RoadmapView; label: string; hint: string }[] = [
  { id: 'journey', label: 'Journey', hint: 'One step at a time' },
  { id: 'browse', label: 'Browse', hint: 'Read the whole thing' },
  { id: 'map', label: 'Map', hint: 'The whole chart, as a chart' },
]

export function RoadmapPanel() {
  const view = useGuideStore((s) => s.roadmapView)
  const setView = useGuideStore((s) => s.setRoadmapView)
  const [dialog, setDialog] = useState<'source' | null>(null)

  // Map owns its own scrolling — it pans and zooms — so the panel becomes a
  // fixed-height column and the page behind it stops scrolling. The reading
  // views stay ordinary documents that scroll.
  const isMap = view === 'map'

  return (
    <div className={`guide-roadmap ${isMap ? 'guide-roadmap--map' : ''}`}>
      <header className="guide-roadmap__header">
        <div className="guide-roadmap__heading">
          <h2 className="guide-roadmap__title">The money roadmap</h2>
          {!isMap && (
            <p className="guide-roadmap__lede">
              A common order for financial priorities — cover the essentials, build a buffer,
              clear expensive debt, then save for what comes next.
            </p>
          )}
        </div>

        <div className="guide-roadmap__controls">
          <button
            type="button"
            className="guide-icon-button"
            onClick={() => setDialog('source')}
            aria-label="Where this comes from"
            title="Where this comes from"
          >
            <Info size={14} />
          </button>

          <div className="guide-viewswitch" role="group" aria-label="Roadmap view">
            {VIEWS.map((v) => (
              <button
                key={v.id}
                type="button"
                className={`guide-viewswitch__button ${view === v.id ? 'guide-viewswitch__button--active' : ''}`}
                aria-pressed={view === v.id}
                title={v.hint}
                onClick={() => setView(v.id)}
              >
                {v.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      <PositionStrip />

      <ol className="guide-legend" aria-label="What the step colours mean">
        {ROADMAP_STEPS.map((s) => (
          <li key={s.step} className="guide-legend__item">
            <span className="guide-legend__dot" style={{ background: stepColor(s.step) }} aria-hidden />
            <span className="guide-legend__label">
              <span className="guide-legend__step">{s.step}</span> {s.label}
            </span>
          </li>
        ))}
      </ol>

      <div className="guide-roadmap__body">
        {view === 'journey' && <RoadmapJourney />}
        {view === 'browse' && <RoadmapBrowse />}
        {view === 'map' && <RoadmapMap />}
      </div>

      <footer className="guide-roadmap__footer">
        <p className="guide-roadmap__meta">{ROADMAP_DISCLAIMER}</p>
      </footer>

      {dialog === 'source' && (
        <GuideDialog title="Where this comes from" onClose={() => setDialog(null)} historyKey="guide-source">
          <p className="guide-dialog__body">
            The order of these steps is adapted from the r/personalfinance{' '}
            <em>Personal Income Spending Flowchart</em> — a community-maintained chart that has
            guided a great many people through the same questions.
          </p>
          <p className="guide-dialog__body">
            The decisions are theirs. The wording here is ours: rewritten to be shorter, to say
            what each step means inside IGAB, and to work on a phone. Figures that change from
            year to year are deliberately left out, so nothing here quietly goes stale.
          </p>
          <a
            className="guide-dialog__link"
            href={ROADMAP_ATTRIBUTION.href}
            target="_blank"
            rel="noreferrer noopener"
          >
            Read the original
            <ExternalLink size={12} aria-hidden />
          </a>
        </GuideDialog>
      )}
    </div>
  )
}
