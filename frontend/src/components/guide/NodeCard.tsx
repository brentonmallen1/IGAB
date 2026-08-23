import { Link } from 'react-router-dom'
import { ChevronDown, ChevronRight, CornerDownRight, HelpCircle, MinusCircle } from 'lucide-react'
import type { RoadmapNode } from '../../content/roadmap'
import type { ConceptInfo, Signal } from '../../api/guide'
import { GlossaryChips } from './GlossaryChips'
import { SignalNote } from './SignalNote'

export type NodeState = 'visible' | 'pending' | 'skipped'

interface Props {
  node: RoadmapNode
  state?: NodeState
  /** Why this node was routed around, if it was. */
  skipReason?: string
  /** Show every branch at once instead of asking for an answer. Browse mode. */
  showAllBranches?: boolean
  answer?: string
  onAnswer?: (answer: string) => void
  onClearAnswer?: () => void
  detailOpen?: boolean
  onToggleDetail?: () => void
  /** What the app worked out about this node's concept, when there is one. */
  signal?: Signal
  concept?: ConceptInfo
  onCorrectSignal?: () => void
}

/**
 * One step of the roadmap, in every view that renders one.
 *
 * The layering is the whole design: title and body are always visible, the
 * reasoning sits behind "Why this matters", and definitions sit behind the
 * term chips. Someone skimming reads two lines per node; someone who wants the
 * depth is two clicks from all of it. Neither is made to scroll past the
 * other's material.
 */
export function NodeCard({
  node,
  state = 'visible',
  skipReason,
  showAllBranches = false,
  answer,
  onAnswer,
  onClearAnswer,
  detailOpen = false,
  onToggleDetail,
  signal,
  concept,
  onCorrectSignal,
}: Props) {
  // Pending and skipped nodes collapse to a single line. They stay on the page
  // — a reader who answered "No" can still see what "Yes" would have led to —
  // but they do not compete with the step actually in front of them.
  if (state === 'skipped') {
    return (
      <div className="guide-node guide-node--muted">
        <MinusCircle size={13} className="guide-node__muted-icon" aria-hidden />
        <span className="guide-node__muted-title">{node.title}</span>
        <span className="guide-node__muted-note">
          {skipReason ? `skipped — you answered “${skipReason}”` : 'skipped'}
        </span>
      </div>
    )
  }

  if (state === 'pending') {
    return (
      <div className="guide-node guide-node--muted">
        <ChevronRight size={13} className="guide-node__muted-icon" aria-hidden />
        <span className="guide-node__muted-title">{node.title}</span>
        <span className="guide-node__muted-note">next, once you answer above</span>
      </div>
    )
  }

  const paragraphs = node.detail?.split('\n\n').filter(Boolean) ?? []
  const detailId = `detail-${node.id}`

  return (
    <article className={`guide-node guide-node--${node.kind}`} id={`node-${node.id}`}>
      {node.kind === 'decision' && <span className="guide-node__kind">Question</span>}
      <h4 className="guide-node__title">{node.title}</h4>
      <p className="guide-node__body">{node.body}</p>

      {node.branches && (
        <div className="guide-branches">
          {showAllBranches || answer === undefined ? (
            node.branches.map((b) => (
              <BranchOption
                key={b.answer}
                answer={b.answer}
                label={b.label}
                interactive={!showAllBranches}
                onSelect={onAnswer ? () => onAnswer(b.answer) : undefined}
              />
            ))
          ) : (
            <div className="guide-branches__chosen">
              <CornerDownRight size={14} aria-hidden />
              <span className="guide-branches__chosen-text">
                You answered <strong>{answer}</strong>
                {chosenLabel(node, answer) && <> — {chosenLabel(node, answer)}</>}
              </span>
              {onClearAnswer && (
                <button type="button" className="guide-link-button" onClick={onClearAnswer}>
                  Change
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {paragraphs.length > 0 && (
        <>
          <button
            type="button"
            className="guide-disclosure"
            aria-expanded={detailOpen}
            aria-controls={detailId}
            onClick={onToggleDetail}
          >
            <HelpCircle size={13} aria-hidden />
            <span>Why this matters</span>
            <ChevronDown
              size={13}
              aria-hidden
              className={`guide-disclosure__chevron ${detailOpen ? 'guide-disclosure__chevron--open' : ''}`}
            />
          </button>
          {detailOpen && (
            <div className="guide-node__detail" id={detailId}>
              {paragraphs.map((p, i) => (
                <p key={i}>{p}</p>
              ))}
            </div>
          )}
        </>
      )}

      {signal && onCorrectSignal && (
        <SignalNote signal={signal} concept={concept} onCorrect={onCorrectSignal} />
      )}

      {node.glossary && node.glossary.length > 0 && <GlossaryChips terms={node.glossary} />}

      {node.appLinks && node.appLinks.length > 0 && (
        <div className="guide-node__links">
          {node.appLinks.map((l) => (
            <Link key={l.to + l.label} to={l.to} className="guide-node__link">
              {l.label}
            </Link>
          ))}
        </div>
      )}
    </article>
  )
}

function BranchOption({
  answer,
  label,
  interactive,
  onSelect,
}: {
  answer: string
  label: string
  interactive: boolean
  onSelect?: () => void
}) {
  const content = (
    <>
      <span className="guide-branch__answer">{answer}</span>
      <span className="guide-branch__label">{label}</span>
    </>
  )
  // Browse renders both outcomes as plain text — there is no question being
  // asked there, so a button would promise an interaction that does nothing.
  if (!interactive) return <div className="guide-branch guide-branch--static">{content}</div>
  return (
    <button type="button" className="guide-branch" onClick={onSelect}>
      {content}
    </button>
  )
}

function chosenLabel(node: RoadmapNode, answer: string): string | undefined {
  return node.branches?.find((b) => b.answer === answer)?.label
}
