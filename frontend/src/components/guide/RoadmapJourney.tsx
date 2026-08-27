import { useEffect, useState } from 'react'
import { ChevronDown, ChevronRight, ArrowDown } from 'lucide-react'
import { ROADMAP, findStage, type RoadmapStage } from '../../content/roadmap'
import { useGuideStore } from '../../stores/guideStore'
import { stagePath } from './journeyPath'
import { stepColor } from './stepColor'
import { NodeCard, type NodeState } from './NodeCard'
import { SignalBindingSheet } from './SignalBindingSheet'
import { useGuideSignalMap } from './useGuideSignalMap'
import { useCheckupLeds } from './useCheckupLeds'
import { useRoadmapPosition } from './useRoadmapPosition'
import { StageStatusChip } from './PositionStrip'
import { StepLed } from './StepLed'
import { StageMark } from './StageMark'
import type { SignalKey } from '../../content/roadmap'
import type { CheckupFinding } from '../../api/guide'
import { stageElementId, type StageVerdict } from './roadmapPosition'

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
  const guide = useGuideSignalMap()
  const { leds } = useCheckupLeds()
  const position = useRoadmapPosition()
  const positionSeen = useGuideStore((s) => s.positionSeen)
  const setPositionSeen = useGuideStore((s) => s.setPositionSeen)
  const [correcting, setCorrecting] = useState<SignalKey | null>(null)

  const concept = correcting ? guide.concepts.get(correcting) : undefined

  // Open the current stage once each time the cursor moves. After that the
  // reader's own folding stands — a stage they closed stays closed until the
  // numbers move them on.
  useEffect(() => {
    if (!position.ready || !position.currentStage || position.currentStage === positionSeen) return
    openStage(position.currentStage)
    setPositionSeen(position.currentStage)
  }, [position.ready, position.currentStage, positionSeen, openStage, setPositionSeen])

  return (
    <>
      <ol className="guide-journey">
        {ROADMAP.map((stage) => (
          <StageRow
            key={stage.id}
            stage={stage}
            open={expandedStages.includes(stage.id)}
            onToggle={() => toggleStage(stage.id)}
            onGoToStage={openStage}
            answers={answers}
            onCorrect={setCorrecting}
            led={leds.get(stage.id)}
            verdict={position.statuses.get(stage.id)}
            current={stage.id === position.currentStage}
          />
        ))}
      </ol>
      {concept && guide.budgetId && (
        <SignalBindingSheet
          budgetId={guide.budgetId}
          concept={concept}
          signal={guide.signals.get(concept.key)}
          onClose={() => setCorrecting(null)}
        />
      )}
    </>
  )
}

function StageRow({
  stage,
  open,
  onToggle,
  onGoToStage,
  answers,
  onCorrect,
  led,
  verdict,
  current,
}: {
  stage: RoadmapStage
  open: boolean
  onToggle: () => void
  onGoToStage: (id: RoadmapStage['id']) => void
  answers: Record<string, string>
  onCorrect: (key: SignalKey) => void
  /** The health finding that marks this stage, if one does. */
  led?: CheckupFinding
  /** Where this stage stands, and whether the reader is on it. */
  verdict?: StageVerdict
  current: boolean
}) {
  const toggleDetail = useGuideStore((s) => s.toggleDetail)
  const expandedDetails = useGuideStore((s) => s.expandedDetails)
  const answer = useGuideStore((s) => s.answer)
  const clearAnswer = useGuideStore((s) => s.clearAnswer)

  const guide = useGuideSignalMap()
  const path = stagePath(stage, answers)
  const mark = guide.progress[stage.id]
  const bodyId = `stage-${stage.id}-body`

  function stateOf(nodeId: string): NodeState {
    if (path.skipped.includes(nodeId)) return 'skipped'
    if (path.pending.includes(nodeId)) return 'pending'
    return 'visible'
  }

  const exitStage = path.exitTo ? findStage(path.exitTo) : null

  return (
    <li
      id={stageElementId('journey', stage.id)}
      className={`guide-stage ${current ? 'guide-stage--current' : ''}`}
      style={{ ['--stage-color' as string]: stepColor(stage.step) }}
    >
      <div className="guide-stage__rail">
        <span className="guide-stage__dot" aria-hidden />
        {led && <StepLed reason={led.title} />}
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
          {/* One status per row: the chip gives way to a mark, shown below. */}
          {!mark && <StageStatusChip verdict={verdict} current={current} />}
        </button>

        {guide.budgetId && (
          <StageMark budgetId={guide.budgetId} stageId={stage.id} mark={mark} showControls={open} />
        )}

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
                signal={node.signal ? guide.signals.get(node.signal) : undefined}
                concept={node.signal ? guide.concepts.get(node.signal) : undefined}
                onCorrectSignal={node.signal ? () => onCorrect(node.signal!) : undefined}
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
