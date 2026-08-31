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

/** How many boxes a packed run puts on one line before wrapping.
 *
 * Four, because that is what the source chart uses for its opening row of
 * essentials — and because a run of plain sequential steps reads far better
 * across the page than as a long vertical stack. */
export const PACK_COLS = 4

/** Shortest run worth packing. Two boxes side by side just look stranded. */
const PACK_MIN = 3

export interface FlowNode {
  node: RoadmapNode
  stage: RoadmapStage
  /** Grid position. With horizontal packing, `col` is where the box sits —
   *  which is no longer the same thing as how far off the spine it is. */
  col: number
  row: number
  /** 0 = on the spine. Drives which edges exist; `col` only draws them. */
  depth: number
  /** Placement order. Rows can hold several boxes, so row is not an order. */
  seq: number
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
  seq: number
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

  // ── Placement ─────────────────────────────────────────────────────────────
  // A run of consecutive plain steps on the spine — no questions, no branches
  // — is laid out horizontally and snakes back on itself, exactly as the
  // source chart draws its opening row of essentials. Everything else takes a
  // row of its own so questions and their branches stay easy to follow.
  const nodes: FlowNode[] = []
  const collapsed: CollapsedStage[] = []
  let row = 0
  let seq = 0

  const place = (node: RoadmapNode, stage: RoadmapStage, col: number, r: number) => {
    nodes.push({
      node,
      stage,
      col,
      row: r,
      depth: depthOf(node.id),
      seq: seq++,
      x: col * (NODE_W + COL_GAP),
      y: r * (NODE_H + ROW_GAP),
    })
  }

  /** A plain step: on the spine, asks nothing, offers no parallel options. */
  const isPlain = (node: RoadmapNode) =>
    depthOf(node.id) === 0 && !node.branches?.length && !optionsOf.has(node.id)

  for (const stage of ROADMAP) {
    if (collapsedSet.has(stage.id)) {
      collapsed.push({ stage, col: 0, row, seq: seq++, x: 0, y: row * (NODE_H + ROW_GAP) })
      row += 1
      continue
    }

    let i = 0
    while (i < stage.nodes.length) {
      // How many plain steps run consecutively from here?
      let runEnd = i
      while (runEnd < stage.nodes.length && isPlain(stage.nodes[runEnd])) runEnd++
      const runLength = runEnd - i

      if (runLength >= PACK_MIN) {
        for (let k = 0; k < runLength; k++) {
          const line = Math.floor(k / PACK_COLS)
          const pos = k % PACK_COLS
          // Odd lines run right to left, so the flow snakes instead of
          // jumping back across the page between rows.
          const col = line % 2 === 0 ? pos : PACK_COLS - 1 - pos
          place(stage.nodes[i + k], stage, col, row + line)
        }
        row += Math.ceil(runLength / PACK_COLS)
        i = runEnd
        continue
      }

      place(stage.nodes[i], stage, depthOf(stage.nodes[i].id), row)
      row += 1
      i += 1
    }
  }

  const byId = new Map(nodes.map((n) => [n.node.id, n]))

  // ── Edges ─────────────────────────────────────────────────────────────────
  const edges: FlowEdge[] = []

  /** First spine node of a stage, following collapse. */
  function stageEntry(stageId: StageId): string | null {
    if (collapsedSet.has(stageId)) return `stage:${stageId}`
    const stage = ROADMAP.find((s) => s.id === stageId)
    const first = stage?.nodes.find((n) => depthOf(n.id) === 0)
    return first?.id ?? stage?.nodes[0]?.id ?? null
  }

  /** The next box on the spine after this one, in placement order.
   *
   * Ordering is by `seq`, not by row: a packed run puts several boxes on the
   * same row, so a row number no longer says what comes next.
   *
   * A spine step and a branch rejoining the spine both land here. Note the
   * source chart actually loops the two 15% outcomes back up to re-ask the
   * question; we rejoin forward to the next spine box instead. Same meaning,
   * and it keeps the diagram acyclic — an upward arrow in a scrolling chart
   * reads as a mistake. */
  function nextSpine(fromSeq: number): string | null {
    const candidates = [
      ...nodes
        .filter((n) => n.seq > fromSeq && n.depth === 0)
        .map((n) => ({ seq: n.seq, id: n.node.id })),
      ...collapsed
        .filter((c) => c.seq > fromSeq)
        .map((c) => ({ seq: c.seq, id: `stage:${c.stage.id}` })),
    ].sort((a, b) => a.seq - b.seq)
    return candidates[0]?.id ?? null
  }

  for (const entry of nodes) {
    const { node, seq: s0, depth: d } = entry

    if (node.branches?.length) {
      for (const b of node.branches) {
        const target = b.toNode ?? (b.toStage ? stageEntry(b.toStage) : null)
        // Two branches can share an outcome ("Yes" and "Not sure" both lead to
        // the same place). One arrow, both labels — two overlapping arrows
        // would just look like a rendering fault.
        if (!target) continue
        const existing = edges.find(
          (e) => e.from === node.id && e.to === target && e.kind === 'branch'
        )
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
      for (const id of forks)
        if (byId.has(id)) edges.push({ from: node.id, to: id, kind: 'branch' })
      continue
    }

    // Otherwise continue to whatever comes next at this column or left of it.
    // From the spine that is the next step; from a branch it is the rejoin.
    const next = nextSpine(s0)
    if (next) edges.push({ from: node.id, to: next, kind: d === 0 ? 'sequence' : 'rejoin' })
  }

  // Collapsed stages sit on the spine and pass straight through.
  for (const c of collapsed) {
    const next = nextSpine(c.seq)
    if (next) edges.push({ from: `stage:${c.stage.id}`, to: next, kind: 'sequence' })
  }

  const maxCol = Math.max(0, ...nodes.map((n) => n.col), ...collapsed.map((c) => c.col))
  const maxRow = Math.max(0, ...nodes.map((n) => n.row), ...collapsed.map((c) => c.row))

  return {
    nodes,
    edges,
    byId,
    collapsed,
    width: (maxCol + 1) * NODE_W + maxCol * COL_GAP,
    height: (maxRow + 1) * NODE_H + maxRow * ROW_GAP,
  }
}
