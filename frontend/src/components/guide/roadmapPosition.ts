import {
  ROADMAP,
  type RoadmapNode,
  type RoadmapStage,
  type SignalKey,
  type StageId,
} from '../../content/roadmap'
import type { CheckupFinding, Signal } from '../../api/guide'
import type { RoadmapView } from '../../stores/guideStore'
import { stageAnswered, stagePath } from './journeyPath'

/**
 * Where the reader is on the roadmap, derived — never a score.
 *
 * Each stage gets one of five verdicts, and the first stage that is still
 * `open` or `undecided` (in roadmap order — the array, not the step numbers,
 * which repeat) is where they are. The rules, in the order they win:
 *
 *  1. The reader's own mark — done or skipped. It always wins, however the
 *     numbers read; `checkupLeds` defers to it the same way.
 *  2. A checkup finding lighting the stage: `open`, said in the finding's
 *     own words.
 *  3. The signals of the nodes actually reached on the reader's path. Any
 *     unmet one: `open`. All met (at least one), or a decision answered in a
 *     way that settles the stage: `settled`. Anything the app cannot tell —
 *     an unanswered question, a concept nothing detects — stays `undecided`,
 *     and the cursor stops there rather than guessing past it.
 *
 * With personalisation off every signal reads `off`, so only marks and the
 * reader's answers move the cursor. Pure, so every rule is a one-line test.
 */

export type StageStatus = 'done' | 'skipped' | 'settled' | 'open' | 'undecided'

export interface StageVerdict {
  status: StageStatus
  /** Why, in a phrase the strip can show beside the stage. */
  reason: string
}

export interface PositionInputs {
  progress: Record<string, 'done' | 'skipped' | undefined>
  /** Stage → the finding lighting it, from `ledStages`. */
  leds: Map<StageId, CheckupFinding>
  signals: Map<SignalKey, Signal>
  /** The reader's local answers to decisions, keyed by node id. */
  answers: Record<string, string>
}

export interface RoadmapPosition {
  statuses: Map<StageId, StageVerdict>
  /** Where the reader is: the first open or undecided stage. Not `current`,
   *  because React tooling reads a `.current` as a ref. */
  currentStage: StageId | null
  /** How many stages sit before the current one. */
  behind: number
}

/** A node's verdict from its signal: true, false, null (unknown), or
 *  undefined when there is nothing to read — no signal, switched off. */
function verdictOf(node: RoadmapNode, signals: Map<SignalKey, Signal>): boolean | null | undefined {
  if (!node.signal) return undefined
  const signal = signals.get(node.signal)
  if (!signal || signal.source === 'off' || !signal.tracked) return undefined
  return node.threshold === 'starter' ? signal.starter_met : signal.met
}

export function stageStatus(stage: RoadmapStage, inputs: PositionInputs): StageVerdict {
  const mark = inputs.progress[stage.id]
  if (mark === 'done') return { status: 'done', reason: 'you marked this done' }
  if (mark === 'skipped') return { status: 'skipped', reason: 'you skipped this' }

  const led = inputs.leds.get(stage.id)
  if (led) return { status: 'open', reason: led.title }

  const path = stagePath(stage, inputs.answers)
  const reached = new Set(path.visible)
  const verdicts = stage.nodes
    .filter((n) => reached.has(n.id))
    .map((n) => verdictOf(n, inputs.signals))
    .filter((v): v is boolean | null => v !== undefined)

  if (verdicts.some((v) => v === false)) return { status: 'open', reason: stage.summary }

  const hasDecisions = stage.nodes.some((n) => n.kind === 'decision')
  const answered = path.exitTo !== null || (hasDecisions && stageAnswered(stage, inputs.answers))
  if (answered) return { status: 'settled', reason: 'you answered' }
  if (verdicts.length > 0 && verdicts.every((v) => v === true)) {
    return { status: 'settled', reason: 'your budget says so' }
  }
  return { status: 'undecided', reason: stage.summary }
}

/** The DOM id a view gives a stage's row, so the strip can scroll to it. */
export function stageElementId(view: RoadmapView, id: StageId): string {
  return view === 'browse' ? `browse-${id}` : `stage-${id}`
}

/** A stage's one-line status, as the dots' tooltips and the chips say it. */
export function stageStatusLabel(verdict: StageVerdict, current: boolean): string {
  if (current) return 'you are here'
  switch (verdict.status) {
    case 'done':
    case 'skipped':
      return verdict.reason
    case 'settled':
      return verdict.reason === 'you answered' ? 'answered' : 'looks done'
    default:
      return 'ahead'
  }
}

export function roadmapPosition(inputs: PositionInputs): RoadmapPosition {
  const statuses = new Map<StageId, StageVerdict>()
  let currentStage: StageId | null = null
  let behind = 0
  ROADMAP.forEach((stage, index) => {
    const verdict = stageStatus(stage, inputs)
    statuses.set(stage.id, verdict)
    if (currentStage === null && (verdict.status === 'open' || verdict.status === 'undecided')) {
      currentStage = stage.id
      behind = index
    }
  })
  if (currentStage === null) behind = ROADMAP.length
  return { statuses, currentStage, behind }
}
