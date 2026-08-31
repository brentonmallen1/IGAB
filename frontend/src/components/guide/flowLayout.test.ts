import { describe, it, expect } from 'vitest'
import { buildFlow, NODE_W, NODE_H } from './flowLayout'
import { ROADMAP } from '../../content/roadmap'

const flow = buildFlow()
const idsInOrder = ROADMAP.flatMap((s) => s.nodes.map((n) => n.id))

function edge(from: string, to: string) {
  return flow.edges.find((e) => e.from === from && e.to === to)
}
function outgoing(from: string) {
  return flow.edges.filter((e) => e.from === from)
}

describe('flow layout', () => {
  it('places every node exactly once, in content order', () => {
    expect(flow.nodes.map((n) => n.node.id)).toEqual(idsInOrder)
  })

  it('keeps the spine in column 0', () => {
    const spine = flow.nodes.filter((n) => n.col === 0).map((n) => n.node.id)
    // Everything the reader passes through by answering their way down.
    expect(spine).toContain('create-budget')
    expect(spine).toContain('match-question')
    expect(spine).toContain('high-interest-question')
    expect(spine).toContain('full-ef')
    expect(spine).toContain('fifteen-percent-question')
    expect(spine).toContain('hsa-question')
  })

  it('puts each yes-branch outcome one column right of its question', () => {
    const pairs: [string, string][] = [
      ['match-question', 'contribute-to-match'],
      ['high-interest-question', 'choose-payoff-method'],
      ['moderate-interest-question', 'pay-moderate-debt'],
      ['large-purchase-question', 'save-for-purchase'],
      ['hsa-question', 'max-hsa'],
      ['college-question', 'college-savings'],
    ]
    for (const [q, a] of pairs) {
      expect(flow.byId.get(a)!.col).toBe(flow.byId.get(q)!.col + 1)
    }
  })

  it('nests the 15% follow-up and its outcomes further right', () => {
    expect(flow.byId.get('fifteen-percent-question')!.col).toBe(0)
    expect(flow.byId.get('employer-plan-question')!.col).toBe(1)
    expect(flow.byId.get('increase-contributions')!.col).toBe(2)
    // The source draws the self-employed box directly below its question, in
    // the same column — it is the "No" continuation, not a second side branch.
    expect(flow.byId.get('self-employed-options')!.col).toBe(1)
  })

  it('forks the final options as siblings rather than a chain', () => {
    // Both can apply; the chart must not imply one comes before the other.
    expect(flow.byId.get('retire-early')!.col).toBe(1)
    expect(flow.byId.get('immediate-goals')!.col).toBe(1)
    expect(edge('your-call', 'retire-early')).toBeTruthy()
    expect(edge('your-call', 'immediate-goals')).toBeTruthy()
    expect(edge('retire-early', 'immediate-goals')).toBeUndefined()
  })

  it('draws the source chart’s branch arrows with their labels', () => {
    expect(edge('match-question', 'contribute-to-match')?.label).toContain('Yes')
    expect(edge('match-question', 'high-interest-question')?.label).toBe('No')
    expect(edge('high-interest-question', 'choose-payoff-method')?.label).toBe('Yes')
    expect(edge('high-interest-question', 'full-ef')?.label).toBe('No')
    expect(edge('fifteen-percent-question', 'hsa-question')?.label).toBe('Yes')
    expect(edge('fifteen-percent-question', 'employer-plan-question')?.label).toBe('No')
  })

  it('merges two answers that share one outcome into a single arrow', () => {
    // "Yes" and "Not sure" both lead to contributing to the match. Two
    // overlapping arrows would read as a rendering fault.
    const e = edge('match-question', 'contribute-to-match')
    expect(e?.label).toBe('Yes / Not sure')
    expect(outgoing('match-question')).toHaveLength(2)
  })

  it('rejoins every branch outcome back onto the spine', () => {
    expect(edge('contribute-to-match', 'high-interest-question')?.kind).toBe('rejoin')
    // The payoff-method branch rejoins the spine at the IGAB-native
    // card-mechanics nodes, which then run in sequence to the emergency fund.
    expect(edge('choose-payoff-method', 'pay-down-card-in-igab')?.kind).toBe('rejoin')
    expect(edge('card-carries-again-note', 'full-ef')?.kind).toBe('sequence')
    expect(edge('pay-moderate-debt', 'roth-vs-traditional')?.kind).toBe('rejoin')
    expect(edge('save-for-purchase', 'fifteen-percent-question')?.kind).toBe('rejoin')
    expect(edge('increase-contributions', 'hsa-question')?.kind).toBe('rejoin')
    expect(edge('self-employed-options', 'hsa-question')?.kind).toBe('rejoin')
    expect(edge('max-hsa', 'college-question')?.kind).toBe('rejoin')
    expect(edge('college-savings', 'your-call')?.kind).toBe('rejoin')
  })

  it('carries the spine across a stage boundary', () => {
    expect(edge('minimum-payments', 'starter-ef')?.kind).toBe('sequence')
    expect(edge('starter-ef', 'nonessential-bills')?.kind).toBe('sequence')
    expect(edge('nonessential-bills', 'match-question')?.kind).toBe('sequence')
  })

  it('gives every decision exactly as many arrows as distinct outcomes', () => {
    for (const { node } of flow.nodes) {
      if (!node.branches?.length) continue
      const distinct = new Set(node.branches.map((b) => b.toNode ?? b.toStage))
      expect(outgoing(node.id)).toHaveLength(distinct.size)
    }
  })

  it('points every edge at something that exists', () => {
    const known = new Set([
      ...flow.nodes.map((n) => n.node.id),
      ...flow.collapsed.map((c) => `stage:${c.stage.id}`),
    ])
    for (const e of flow.edges) {
      expect(known.has(e.from)).toBe(true)
      expect(known.has(e.to)).toBe(true)
    }
  })

  it('never draws an arrow that goes backwards', () => {
    // The roadmap is a DAG that flows forward. Packed runs share a row, so
    // the invariant is on placement order — and a row may never decrease.
    for (const e of flow.edges) {
      const from = flow.byId.get(e.from)
      const to = flow.byId.get(e.to)
      if (!from || !to) continue
      expect(to.seq).toBeGreaterThan(from.seq)
      expect(to.row).toBeGreaterThanOrEqual(from.row)
    }
  })

  it('packs the opening run of plain steps horizontally', () => {
    // The source chart lays its essentials out across the page rather than
    // as a tall stack; a run of plain sequential steps should do the same.
    const foundation = flow.nodes.filter((n) => n.stage.id === 'foundation')
    expect(foundation).toHaveLength(7)
    // Four across, then the remainder on a second line.
    expect(foundation.slice(0, 4).map((n) => n.col)).toEqual([0, 1, 2, 3])
    expect(new Set(foundation.slice(0, 4).map((n) => n.row)).size).toBe(1)
    expect(new Set(foundation.slice(4).map((n) => n.row)).size).toBe(1)
    expect(foundation[0].row).not.toBe(foundation[4].row)
  })

  it('snakes the second line back the other way', () => {
    // Left-to-right then right-to-left, so the eye follows the flow instead
    // of jumping the full width of the page between lines.
    const foundation = flow.nodes.filter((n) => n.stage.id === 'foundation')
    expect(foundation.slice(4).map((n) => n.col)).toEqual([3, 2, 1])
  })

  it('keeps packed steps on the spine despite their column', () => {
    // Column is where a box sits; depth is whether it is on the main path.
    // Packing moves the first but must not move the second.
    for (const n of flow.nodes.filter((x) => x.stage.id === 'foundation')) {
      expect(n.depth).toBe(0)
    }
  })

  it('chains packed steps in reading order', () => {
    const chain = [
      'create-budget',
      'housing',
      'groceries',
      'essential-items',
      'income-earning-expenses',
      'health-care',
      'minimum-payments',
    ]
    for (let i = 0; i < chain.length - 1; i++) {
      expect(edge(chain[i], chain[i + 1])?.kind).toBe('sequence')
    }
  })

  it('does not pack a run shorter than three', () => {
    // Two boxes side by side just look stranded.
    const starter = flow.nodes.filter((n) => n.stage.id === 'starter-emergency-fund')
    expect(starter).toHaveLength(2)
    expect(starter[0].row).not.toBe(starter[1].row)
    expect(starter.every((n) => n.col === 0)).toBe(true)
  })

  it('never overlaps two boxes', () => {
    const seen = new Set<string>()
    for (const n of [...flow.nodes, ...flow.collapsed]) {
      const key = `${n.row}:${n.col}`
      expect(seen.has(key)).toBe(false)
      seen.add(key)
    }
  })

  it('leaves no node stranded without an inbound arrow, except the first', () => {
    const targeted = new Set(flow.edges.map((e) => e.to))
    const orphans = flow.nodes.map((n) => n.node.id).filter((id, i) => i > 0 && !targeted.has(id))
    expect(orphans).toEqual([])
  })

  it('sizes the canvas to fit every node', () => {
    for (const n of flow.nodes) {
      expect(n.x + NODE_W).toBeLessThanOrEqual(flow.width)
      expect(n.y + NODE_H).toBeLessThanOrEqual(flow.height)
    }
  })

  describe('collapsing', () => {
    const partial = buildFlow(['foundation'])

    it('keeps the No-continuation answers on the spine', () => {
      // hsa-question's "No" and college-question's "No" carry the reader
      // onward, so their targets stay in column 0 rather than stepping right.
      expect(flow.byId.get('college-question')!.col).toBe(0)
      expect(flow.byId.get('your-call')!.col).toBe(0)
    })

    it('replaces a stage with a single box', () => {
      expect(partial.collapsed.map((c) => c.stage.id)).toEqual(['foundation'])
      expect(partial.nodes.find((n) => n.stage.id === 'foundation')).toBeUndefined()
      expect(partial.nodes).toHaveLength(flow.nodes.length - 7)
    })

    it('keeps the chart connected through the collapsed box', () => {
      expect(edgeIn(partial, 'stage:foundation', 'starter-ef')).toBeTruthy()
    })

    it('shrinks the canvas', () => {
      expect(partial.height).toBeLessThan(flow.height)
    })

    it('survives every stage being collapsed at once', () => {
      const all = buildFlow(ROADMAP.map((s) => s.id))
      expect(all.nodes).toHaveLength(0)
      expect(all.collapsed).toHaveLength(ROADMAP.length)
      // Still a connected spine, one box per stage.
      expect(all.edges).toHaveLength(ROADMAP.length - 1)
    })
  })
})

function edgeIn(f: ReturnType<typeof buildFlow>, from: string, to: string) {
  return f.edges.find((e) => e.from === from && e.to === to)
}
