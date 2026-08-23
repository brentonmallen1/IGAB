import type { RoadmapStage, StageId } from '../../content/roadmap'

/**
 * Which nodes a reader actually sees in Journey view, given the answers they
 * have given so far.
 *
 * Journey shows one thing at a time. That means three states, not two:
 *
 *  - **visible** — on the path. Rendered in full.
 *  - **pending** — sits after an unanswered decision. Rendered as a muted
 *    title only. Shown rather than hidden so the stage never looks truncated
 *    and the reader can see what is coming without being asked to act on it.
 *  - **skipped** — an answer routed around it. Still listed, collapsed, with
 *    the reason. Nothing is ever removed from the page: a reader who answers
 *    "No" should still be able to see what "Yes" would have led to.
 *
 * `exitTo` is set when an answer leaves the stage entirely, so the caller can
 * say where the reader is being sent rather than silently ending the stage.
 */
export interface StagePath {
  visible: string[]
  pending: string[]
  skipped: string[]
  /** Node id -> the answer that caused it to be skipped. */
  skipReason: Record<string, string>
  exitTo: StageId | null
}

export function stagePath(stage: RoadmapStage, answers: Record<string, string>): StagePath {
  const visible: string[] = []
  const pending: string[] = []
  const skipped: string[] = []
  const skipReason: Record<string, string> = {}
  let exitTo: StageId | null = null

  const index = new Map(stage.nodes.map((n, i) => [n.id, i]))
  let i = 0

  while (i < stage.nodes.length) {
    const node = stage.nodes[i]
    visible.push(node.id)

    if (node.kind !== 'decision' || !node.branches) {
      i += 1
      continue
    }

    const given = answers[node.id]
    if (given === undefined) {
      // Unanswered: everything after this is on hold, not decided against.
      for (let j = i + 1; j < stage.nodes.length; j++) pending.push(stage.nodes[j].id)
      break
    }

    const branch = node.branches.find((b) => b.answer === given)
    if (!branch) {
      // A stored answer that no longer matches any branch — the content was
      // edited under the reader. Treat it as unanswered rather than crashing.
      for (let j = i + 1; j < stage.nodes.length; j++) pending.push(stage.nodes[j].id)
      break
    }

    if (branch.toStage) {
      for (let j = i + 1; j < stage.nodes.length; j++) {
        skipped.push(stage.nodes[j].id)
        skipReason[stage.nodes[j].id] = given
      }
      exitTo = branch.toStage
      break
    }

    if (branch.toNode) {
      const target = index.get(branch.toNode)
      // A forward jump skips what it steps over. A target that is missing or
      // behind us cannot route anything, so just continue in order — the
      // content tests catch both cases before this ever ships.
      if (target === undefined || target <= i) {
        i += 1
        continue
      }
      for (let j = i + 1; j < target; j++) {
        skipped.push(stage.nodes[j].id)
        skipReason[stage.nodes[j].id] = given
      }
      i = target
      continue
    }

    i += 1
  }

  return { visible, pending, skipped, skipReason, exitTo }
}

/** True when every decision in the stage has been answered. */
export function stageAnswered(stage: RoadmapStage, answers: Record<string, string>): boolean {
  const path = stagePath(stage, answers)
  const reached = new Set(path.visible)
  return stage.nodes
    .filter((n) => n.kind === 'decision' && reached.has(n.id))
    .every((n) => answers[n.id] !== undefined)
}
