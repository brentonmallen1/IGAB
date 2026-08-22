import { ChevronDown, ChevronRight, Check, ArrowDown } from 'lucide-react'
import { ROADMAP, findStage, type RoadmapStage } from '../../content/roadmap'
import { useGuideStore } from '../../stores/guideStore'
import { stagePath, stageAnswered } from './journeyPath'
import { stepColor } from './stepColor'
import { NodeCard, type NodeState } from './NodeCard'

/**
 * The roadmap as a path you walk — one stage at a time, collapsed by default.
 *
 * This is the default view because the most common question is "what next?",
 * and a wall of every step at once answers it badly. Browse mode exists for
 * the opposite need and carries identical content.
 */
export function RoadmapJourney() {
  const expandedStages = useGuideStore((s) => s.expandedStages)
  const toggleStage = useGuideStore((s) => s.toggleStage)
  const openStage = useGuideStore((s) => s.openStage)
  const answers = useGuideStore((s) => s.answers)

  return (
    <ol className="guide-journey">
      {ROADMAP.map((stage) => (
        <StageRow
          key={stage.id}
          stage={stage}
          open={expandedStages.includes(stage.id)}
          onToggle={() => toggleStage(stage.id)}
          onGoToStage={openStage}
          answers={answers}
        />
      ))}
    </ol>
  )
}

function StageRow({
  stage,
  open,
  onToggle,
  onGoToStage,
  answers,
}: {
  stage: RoadmapStage
  open: boolean
  onToggle: () => void
  onGoToStage: (id: RoadmapStage['id']) => void
  answers: Record<string, string>
}) {
  const toggleDetail = useGuideStore((s) => s.toggleDetail)
  const expandedDetails = useGuideStore((s) => s.expandedDetails)
  const answer = useGuideStore((s) => s.answer)
  const clearAnswer = useGuideStore((s) => s.clearAnswer)

  const path = stagePath(stage, answers)
  const done = stageAnswered(stage, answers) && stage.nodes.some((n) => n.kind === 'decision')
  const bodyId = `stage-${stage.id}`

  function stateOf(nodeId: string): NodeState {
    if (path.skipped.includes(nodeId)) return 'skipped'
    if (path.pending.includes(nodeId)) return 'pending'
    return 'visible'
  }

  const exitStage = path.exitTo ? findStage(path.exitTo) : null

  return (
    <li className="guide-stage" style={{ ['--stage-color' as string]: stepColor(stage.step) }}>
      <div className="guide-stage__rail" aria-hidden>
        <span className="guide-stage__dot" />
      </div>

      <div className="guide-stage__main">
        <button
          type="button"
          className="guide-stage__header"
          aria-expanded={open}
          aria-controls={bodyId}
          onClick={onToggle}
        >
          <span className="guide-stage__chevron" aria-hidden>
            {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </span>
          <span className="guide-stage__step">Step {stage.step}</span>
          <span className="guide-stage__title">{stage.title}</span>
          {done && (
            <span className="guide-stage__done" title="You have answered this stage">
              <Check size={12} aria-hidden />
              answered
            </span>
          )}
        </button>

        {/* The summary stays visible when collapsed — the whole stage in a
            breath, so scanning the roadmap is useful without opening anything. */}
        {!open && <p className="guide-stage__summary">{stage.summary}</p>}

        {open && (
          <div className="guide-stage__body" id={bodyId}>
            <p className="guide-stage__summary guide-stage__summary--open">{stage.summary}</p>
            {stage.nodes.map((node) => (
              <NodeCard
                key={node.id}
                node={node}
                state={stateOf(node.id)}
                skipReason={path.skipReason[node.id]}
                answer={answers[node.id]}
                onAnswer={(a) => answer(node.id, a)}
                onClearAnswer={() => clearAnswer(node.id)}
                detailOpen={expandedDetails.includes(node.id)}
                onToggleDetail={() => toggleDetail(node.id)}
              />
            ))}

            {exitStage && (
              <button
                type="button"
                className="guide-stage__exit"
                onClick={() => onGoToStage(exitStage.id)}
              >
                <ArrowDown size={13} aria-hidden />
                Your answer sends you to Step {exitStage.step} — {exitStage.title}
              </button>
            )}
          </div>
        )}
      </div>
    </li>
  )
}
