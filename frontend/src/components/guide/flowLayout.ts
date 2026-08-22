import { ROADMAP, type RoadmapNode, type RoadmapStage, type StageId } from '../../content/roadmap'

/**
 * Turns the roadmap content into an actual flowchart — boxes and arrows.
 *
 * Everything here is *derived* from the same content the other views render.
 * There is no second list of edges to keep in sync: an edge exists because a
 * branch exists. That is the whole point — a hand-maintained diagram drifts
 * from the content it illustrates, usually silently, and a wrong arrow in a
 * finance flowchart is worse than no diagram at all.
 *
 * ── Columns ─────────────────────────────────────────────────────────────────
 * Column 0 is the spine: the path you are on if you answer every question in
 * the way that keeps you moving down. A node that some decision jumps *to*
 * sits one column right of that decision, so a "Yes" branch reads left to
 * right and the spine stays a straight line down the page. Nesting works —
 * the 15% question's follow-up is itself a decision, and its outcomes land in
 * column 2.
 *
 * ── Rows ────────────────────────────────────────────────────────────────────
 * One row per node, in content order. Deliberately not compacted: keeping row
 * order identical to reading order means the diagram and the Browse view tell
 * the same story in the same sequence.
 */

export const NODE_W = 208
export const NODE_H = 78
export const COL_GAP = 64
export const ROW_GAP = 26

export interface FlowNode {
  node: RoadmapNode
  stage: RoadmapStage
  col: number
  row: number
  x: number
  y: number
}

export type EdgeKind = 'sequence' | 'branch' | 'rejoin'

export interface FlowEdge {
  from: string
  to: string
  kind: EdgeKind
  /** "Yes" / "No" — only on branch edges. */
  label?: string
}

export interface FlowLayout {
  nodes: FlowNode[]
  edges: FlowEdge[]
  byId: Map<string, FlowNode>
  width: number
  height: number
}

/** A stage rendered as one box instead of its nodes. */
export interface CollapsedStage {
  stage: RoadmapStage
  col: 0
  row: number
  x: number
  y: number
}

export interface FlowResult extends FlowLayout {
  collapsed: CollapsedStage[]
}

/**
 * @param collapsedStages stages to draw as a single box. Collapsing is what
 *   makes a 30-node chart fit on a laptop screen without zooming out to
 *   unreadable.
 */
export function buildFlow(collapsedStages: StageId[] = []): FlowResult {
  const collapsedSet = new Set(collapsedStages)

  // ── Columns: how far right a node sits ───────────────────────────────────
  // A decision has two kinds of outgoing branch, and the source chart draws
  // them differently:
  //
  //   * the branch to the node *immediately* after it is the side branch —
  //     "Yes, do this thing" — and steps one column right;
  //   * any other branch is the decision continuing onward, and stays in the
  //     column it is already in.
  //
  // That single rule reproduces the original layout exactly, including the
  // nested 15% question: its "No" opens a sub-question one column right, whose
  // own "Yes" steps right again while its "No" stays alongside it.
  const rule = new Map<string, { parent: string; step: 0 | 1 }>()
  const optionsOf = new Map<string, string[]>()

  for (const stage of ROADMAP) {
    stage.nodes.forEach((node, i) => {
      const nextId = stage.nodes[i + 1]?.id
      for (const b of node.branches ?? []) {
        if (!b.toNode || rule.has(b.toNode)) continue
        rule.set(b.toNode, { parent: node.id, step: b.toNode === nextId ? 1 : 0 })
      }
    })
    // `option` nodes fork off the last non-option node before them — they are
    // siblings of each other, not a chain, so they share a parent and a column.
    stage.nodes.forEach((node, i) => {
      if (!node.option) return
      for (let j = i - 1; j >= 0; j--) {
        if (stage.nodes[j].option) continue
        const parent = stage.nodes[j].id
        rule.set(node.id, { parent, step: 1 })
        optionsOf.set(parent, [...(optionsOf.get(parent) ?? []), node.id])
        return
      }
    })
  }

  const depth = new Map<string, number>()
  function depthOf(id: string, seen = new Set<string>()): number {
    const cached = depth.get(id)
    if (cached !== undefined) return cached
    if (seen.has(id)) return 0 // cycle guard; content tests forbid these
    seen.add(id)
    const r = rule.get(id)
    const d = r === undefined ? 0 : depthOf(r.parent, seen) + r.step
    depth.set(id, d)
    return d
  }

  // ── Rows: content order, with collapsed stages taking one row each ────────
  const nodes: FlowNode[] = []
  const collapsed: CollapsedStage[] = []
  let row = 0

  for (const stage of ROADMAP) {
    if (collapsedSet.has(stage.id)) {
      collapsed.push({ stage, col: 0, row, x: 0, y: row * (NODE_H + ROW_GAP) })
      row += 1
      continue
    }
    for (const node of stage.nodes) {
      const col = depthOf(node.id)
      nodes.push({
        node,
        stage,
        col,
        row,
        x: col * (NODE_W + COL_GAP),
        y: row * (NODE_H + ROW_GAP),
      })
      row += 1
    }
  }

  const byId = new Map(nodes.map((n) => [n.node.id, n]))

  // ── Edges ─────────────────────────────────────────────────────────────────
  const edges: FlowEdge[] = []

  /** First spine (column 0) node of a stage, following collapse. */
  function stageEntry(stageId: StageId): string | null {
    if (collapsedSet.has(stageId)) return `stage:${stageId}`
    const stage = ROADMAP.find((s) => s.id === stageId)
    const first = stage?.nodes.find((n) => depthOf(n.id) === 0)
    return first?.id ?? stage?.nodes[0]?.id ?? null
  }

  /** The next box on the spine below this row.
   *
   * Both a spine step and a branch rejoining it land in the same place, so
   * this is one function. Note the source chart actually loops the two 15%
   * outcomes back up to re-ask the question; we rejoin forward to the next
   * spine node instead. Same meaning, and it keeps the diagram acyclic —
   * an upward arrow in a scrolling chart reads as a mistake. */
  function nextSpine(fromRow: number): string | null {
    const candidates = [
      ...nodes.filter((n) => n.row > fromRow && n.col === 0).map((n) => ({ row: n.row, id: n.node.id })),
      ...collapsed.filter((c) => c.row > fromRow).map((c) => ({ row: c.row, id: `stage:${c.stage.id}` })),
    ].sort((a, b) => a.row - b.row)
    return candidates[0]?.id ?? null
  }

  for (const entry of nodes) {
    const { node, row: r, col } = entry

    if (node.branches?.length) {
      for (const b of node.branches) {
        const target = b.toNode ?? (b.toStage ? stageEntry(b.toStage) : null)
        // Two branches can share an outcome ("Yes" and "Not sure" both lead to
        // the same place). One arrow, both labels — two overlapping arrows
        // would just look like a rendering fault.
        if (!target) continue
        const existing = edges.find((e) => e.from === node.id && e.to === target && e.kind === 'branch')
        if (existing) {
          existing.label = `${existing.label} / ${b.answer}`
          continue
        }
        edges.push({ from: node.id, to: target, kind: 'branch', label: b.answer })
      }
      continue
    }

    // A node that offers parallel options forks to all of them at once —
    // there is no ordering between them and the chart should not imply one.
    const forks = optionsOf.get(node.id)
    if (forks?.length) {
      for (const id of forks) if (byId.has(id)) edges.push({ from: node.id, to: id, kind: 'branch' })
      continue
    }

    // Otherwise continue to whatever comes next at this column or left of it.
    // From the spine that is the next step; from a branch it is the rejoin.
    const next = nextSpine(r)
    if (next) edges.push({ from: node.id, to: next, kind: col === 0 ? 'sequence' : 'rejoin' })
  }

  // Collapsed stages sit on the spine and pass straight through.
  for (const c of collapsed) {
    const next = nextSpine(c.row)
    if (next) edges.push({ from: `stage:${c.stage.id}`, to: next, kind: 'sequence' })
  }

  const maxCol = Math.max(0, ...nodes.map((n) => n.col))
  const totalRows = row

  return {
    nodes,
    edges,
    byId,
    collapsed,
    width: (maxCol + 1) * NODE_W + maxCol * COL_GAP,
    height: totalRows * NODE_H + Math.max(0, totalRows - 1) * ROW_GAP,
  }
}
