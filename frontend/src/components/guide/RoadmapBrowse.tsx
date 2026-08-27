import { useState } from 'react'
import { ROADMAP } from '../../content/roadmap'
import { useGuideStore } from '../../stores/guideStore'
import { stepColor } from './stepColor'
import { NodeCard } from './NodeCard'
import { SignalBindingSheet } from './SignalBindingSheet'
import { useGuideSignalMap } from './useGuideSignalMap'
import { useCheckupLeds } from './useCheckupLeds'
import { useRoadmapPosition } from './useRoadmapPosition'
import { StageStatusChip } from './PositionStrip'
import { stageElementId } from './roadmapPosition'
import { StepLed } from './StepLed'
import { StageMark } from './StageMark'
import type { SignalKey } from '../../content/roadmap'

/**
 * The whole roadmap, open, in reading order — including both sides of every
 * decision.
 *
 * Journey asks you to make choices to move forward. Some people want to read
 * the thing end to end first, or go back and look at a branch they did not
 * take. This view carries exactly the same content with nothing gated, which
 * is also what makes it the accessible floor: every node is reachable here
 * without interacting with anything.
 */
export function RoadmapBrowse() {
  const expandedDetails = useGuideStore((s) => s.expandedDetails)
  const toggleDetail = useGuideStore((s) => s.toggleDetail)
  // Browse opens everything by default; this only tracks stages the reader has
  // deliberately folded away to get them out of the way.
  const [collapsed, setCollapsed] = useState<string[]>([])
  const guide = useGuideSignalMap()
  const { leds } = useCheckupLeds()
  const position = useRoadmapPosition()
  const [correcting, setCorrecting] = useState<SignalKey | null>(null)
  const concept = correcting ? guide.concepts.get(correcting) : undefined

  return (
    <div className="guide-browse">
      {ROADMAP.map((stage) => {
        const isCollapsed = collapsed.includes(stage.id)
        const led = leds.get(stage.id)
        const current = stage.id === position.currentStage
        const mark = guide.progress[stage.id]
        return (
          <section
            key={stage.id}
            className={`guide-browse__stage ${current ? 'guide-browse__stage--current' : ''}`}
            style={{ ['--stage-color' as string]: stepColor(stage.step) }}
            aria-labelledby={stageElementId('browse', stage.id)}
          >
            <div className="guide-browse__header">
              <span className="guide-browse__step">
                Step {stage.step}
                {led && <StepLed reason={led.title} />}
              </span>
              <h3 className="guide-browse__title" id={stageElementId('browse', stage.id)}>
                {stage.title}
              </h3>
              {!mark && (
                <StageStatusChip verdict={position.statuses.get(stage.id)} current={current} />
              )}
              <button
                type="button"
                className="guide-link-button guide-browse__fold"
                onClick={() =>
                  setCollapsed((c) =>
                    c.includes(stage.id) ? c.filter((x) => x !== stage.id) : [...c, stage.id]
                  )
                }
                aria-expanded={!isCollapsed}
              >
                {isCollapsed ? 'Show' : 'Hide'}
              </button>
            </div>
            <p className="guide-browse__summary">{stage.summary}</p>
            {guide.budgetId && (
              <StageMark
                budgetId={guide.budgetId}
                stageId={stage.id}
                mark={mark}
                showControls={!isCollapsed}
              />
            )}

            {!isCollapsed &&
              stage.nodes.map((node) => (
                <NodeCard
                  key={node.id}
                  node={node}
                  showAllBranches
                  detailOpen={expandedDetails.includes(node.id)}
                  onToggleDetail={() => toggleDetail(node.id)}
                  signal={node.signal ? guide.signals.get(node.signal) : undefined}
                  concept={node.signal ? guide.concepts.get(node.signal) : undefined}
                  onCorrectSignal={node.signal ? () => setCorrecting(node.signal!) : undefined}
                />
              ))}
          </section>
        )
      })}
      {concept && guide.budgetId && (
        <SignalBindingSheet
          budgetId={guide.budgetId}
          concept={concept}
          signal={guide.signals.get(concept.key)}
          onClose={() => setCorrecting(null)}
        />
      )}
    </div>
  )
}
