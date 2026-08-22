import { ExternalLink } from 'lucide-react'
import {
  ROADMAP_STEPS,
  ROADMAP_ATTRIBUTION,
  ROADMAP_DISCLAIMER,
  DISCRETIONARY_NOTE,
} from '../../content/roadmap'
import { useGuideStore, type RoadmapView } from '../../stores/guideStore'
import { stepColor } from './stepColor'
import { RoadmapJourney } from './RoadmapJourney'
import { RoadmapBrowse } from './RoadmapBrowse'

const VIEWS: { id: RoadmapView; label: string; hint: string }[] = [
  { id: 'journey', label: 'Journey', hint: 'One step at a time' },
  { id: 'browse', label: 'Browse', hint: 'Read the whole thing' },
]

export function RoadmapPanel() {
  const view = useGuideStore((s) => s.roadmapView)
  const setView = useGuideStore((s) => s.setRoadmapView)

  return (
    <div className="guide-roadmap">
      <header className="guide-roadmap__header">
        <div>
          <h2 className="guide-roadmap__title">The money roadmap</h2>
          <p className="guide-roadmap__lede">
            A common order for financial priorities — cover the essentials, build a buffer,
            clear expensive debt, then save for what comes next.
          </p>
        </div>

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
      </header>

      <ol className="guide-legend" aria-label="What the step colours mean">
        {ROADMAP_STEPS.map((s) => (
          <li key={s.step} className="guide-legend__item">
            <span
              className="guide-legend__dot"
              style={{ background: stepColor(s.step) }}
              aria-hidden
            />
            <span className="guide-legend__label">
              <span className="guide-legend__step">{s.step}</span> {s.label}
            </span>
          </li>
        ))}
      </ol>

      {view === 'journey' ? <RoadmapJourney /> : <RoadmapBrowse />}

      <footer className="guide-roadmap__footer">
        <p className="guide-roadmap__note">{DISCRETIONARY_NOTE}</p>
        <p className="guide-roadmap__meta">
          <a
            className="guide-roadmap__source"
            href={ROADMAP_ATTRIBUTION.href}
            target="_blank"
            rel="noreferrer noopener"
          >
            {ROADMAP_ATTRIBUTION.text}
            <ExternalLink size={11} aria-hidden />
          </a>
        </p>
        <p className="guide-roadmap__meta">{ROADMAP_DISCLAIMER}</p>
      </footer>
    </div>
  )
}
