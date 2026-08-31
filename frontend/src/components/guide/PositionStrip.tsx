import { Check, Minus } from 'lucide-react'
import { ROADMAP, findStage, type StageId } from '../../content/roadmap'
import { useGuideStore, type RoadmapView } from '../../stores/guideStore'
import { prefersReducedMotion } from '../../utils/motion'
import { stepColor } from './stepColor'
import { useRoadmapPosition } from './useRoadmapPosition'
import { stageElementId, stageStatusLabel, type StageVerdict } from './roadmapPosition'

/**
 * "Where you are": one row of stage dots above the roadmap, and a caption
 * naming the current stage and why. Shape carries the state — filled,
 * ring, hollow, dash — so the step colours stay what they are, a key to the
 * legend, and nothing here depends on telling amber from green.
 *
 * Every dot and the caption jump to the stage. The Map cannot scroll to a
 * box, so from there the jump lands in Journey.
 */

function scrollToStage(view: RoadmapView, id: StageId) {
  // The row may not exist until the view re-renders (a stage just opened,
  // a switch from the Map) — look for it on the next frame.
  requestAnimationFrame(() => {
    document
      .getElementById(stageElementId(view, id))
      ?.scrollIntoView({ block: 'start', behavior: prefersReducedMotion() ? 'auto' : 'smooth' })
  })
}

/** The quiet chip on a stage row: "you are here", or how it was settled. */
export function StageStatusChip({
  verdict,
  current,
}: {
  verdict?: StageVerdict
  current: boolean
}) {
  if (current) return <span className="guide-stage__here">you are here</span>
  if (verdict?.status !== 'settled') return null
  return (
    <span
      className="guide-stage__done"
      title={
        verdict.reason === 'you answered'
          ? 'You have answered this stage'
          : 'Your budget’s numbers satisfy this step'
      }
    >
      <Check size={12} aria-hidden />
      {stageStatusLabel(verdict, false)}
    </span>
  )
}

/** The reader's mark as a glyph, for the Map's boxes. */
export function MarkGlyph({ mark }: { mark?: 'done' | 'skipped' }) {
  if (mark === 'done')
    return <Check size={9} className="guide-mark-glyph" aria-label="you marked this done" />
  if (mark === 'skipped')
    return <Minus size={9} className="guide-mark-glyph" aria-label="you skipped this" />
  return null
}

export function PositionStrip() {
  const position = useRoadmapPosition()
  const view = useGuideStore((s) => s.roadmapView)
  const setView = useGuideStore((s) => s.setRoadmapView)
  const openStage = useGuideStore((s) => s.openStage)

  const current = position.currentStage ? findStage(position.currentStage) : null
  const why = position.currentStage
    ? position.statuses.get(position.currentStage)?.reason
    : undefined

  function goTo(id: StageId) {
    const target: RoadmapView = view === 'map' ? 'journey' : view
    if (target !== view) setView(target)
    openStage(id)
    scrollToStage(target, id)
  }

  return (
    <nav className="guide-position" aria-label="Where you are on the roadmap">
      <ol className="guide-position__dots">
        {ROADMAP.map((stage) => {
          const verdict = position.statuses.get(stage.id)
          if (!verdict) return null
          const isCurrent = stage.id === position.currentStage
          const state = isCurrent
            ? 'current'
            : verdict.status === 'open' || verdict.status === 'undecided'
              ? 'ahead'
              : verdict.status
          const label = stageStatusLabel(verdict, isCurrent)
          return (
            <li key={stage.id}>
              <button
                type="button"
                className={`guide-position__dot guide-position__dot--${state}`}
                style={{ ['--stage-color' as string]: stepColor(stage.step) }}
                onClick={() => goTo(stage.id)}
                title={`Step ${stage.step} — ${stage.title} · ${label}`}
                aria-label={`Step ${stage.step} — ${stage.title}: ${label}`}
                aria-current={isCurrent ? 'step' : undefined}
              >
                {verdict.status === 'done' && <Check size={7} aria-hidden />}
                {verdict.status === 'skipped' && <Minus size={7} aria-hidden />}
              </button>
            </li>
          )
        })}
      </ol>
      <p className="guide-position__caption">
        {current ? (
          <>
            <button
              type="button"
              className="guide-link-button guide-position__where"
              onClick={() => goTo(current.id)}
            >
              You’re on Step {current.step} — {current.title}
            </button>
            <span className="guide-position__why">
              {why && ` · ${why}`}
              {position.behind > 0 &&
                ` · ${position.behind} of ${ROADMAP.length} stages behind you`}
            </span>
          </>
        ) : (
          <span className="guide-position__why">
            Nothing left the roadmap can see — mark steps as you go.
          </span>
        )}
      </p>
    </nav>
  )
}
