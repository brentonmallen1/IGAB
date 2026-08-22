import { describe, it, expect } from 'vitest'
import {
  ROADMAP,
  ROADMAP_STEPS,
  findNode,
  findStage,
  type RoadmapNode,
} from './roadmap'
import { GLOSSARY, GLOSSARY_IDS, glossaryEntry, searchGlossary } from './glossary'

/** The roadmap and glossary are hand-authored prose, and the usual failure is
 *  not a crash — it is a dead link, an unreachable node, or a decision whose
 *  "Yes" leads nowhere. Those read as working software right up until a user
 *  hits them. These tests are the proofreader. */

const allNodes: RoadmapNode[] = ROADMAP.flatMap((s) => s.nodes)

describe('glossary integrity', () => {
  it('has an entry for every declared id', () => {
    const defined = new Set(GLOSSARY.map((e) => e.id))
    const missing = GLOSSARY_IDS.filter((id) => !defined.has(id))
    expect(missing).toEqual([])
  })

  it('declares every entry it defines', () => {
    const declared = new Set<string>(GLOSSARY_IDS)
    const undeclared = GLOSSARY.map((e) => e.id).filter((id) => !declared.has(id))
    expect(undeclared).toEqual([])
  })

  it('has no duplicate ids', () => {
    const ids = GLOSSARY.map((e) => e.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('resolves every related-term link', () => {
    const dangling: string[] = []
    for (const entry of GLOSSARY) {
      for (const rel of entry.related ?? []) {
        if (!glossaryEntry(rel)) dangling.push(`${entry.id} -> ${rel}`)
      }
    }
    expect(dangling).toEqual([])
  })

  it('never lists itself as a related term', () => {
    const selfRefs = GLOSSARY.filter((e) => (e.related ?? []).includes(e.id)).map((e) => e.id)
    expect(selfRefs).toEqual([])
  })

  it('keeps the one-line summary short enough to sit in a tooltip', () => {
    const tooLong = GLOSSARY.filter((e) => e.short.length > 120).map((e) => e.id)
    expect(tooLong).toEqual([])
  })

  it('gives every entry a real body', () => {
    const thin = GLOSSARY.filter((e) => e.body.trim().length < 40).map((e) => e.id)
    expect(thin).toEqual([])
  })

  it('matches on term, alias and summary text', () => {
    expect(searchGlossary('avalanche').map((e) => e.id)).toContain('avalanche')
    // alias
    expect(searchGlossary('rainy day').map((e) => e.id)).toContain('emergency-fund')
    // case-insensitive
    expect(searchGlossary('APR').map((e) => e.id)).toContain('apr')
    // empty query returns everything rather than nothing
    expect(searchGlossary('   ')).toHaveLength(GLOSSARY.length)
  })
})

describe('roadmap integrity', () => {
  it('has no duplicate stage ids', () => {
    const ids = ROADMAP.map((s) => s.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('has globally unique node ids', () => {
    // findNode() searches every stage, so ids must be unique across the whole
    // roadmap, not merely within a stage.
    const ids = allNodes.map((n) => n.id)
    const seen = new Set<string>()
    const dupes = ids.filter((id) => (seen.has(id) ? true : (seen.add(id), false)))
    expect(dupes).toEqual([])
  })

  it('resolves every branch target', () => {
    const dangling: string[] = []
    for (const stage of ROADMAP) {
      for (const node of stage.nodes) {
        for (const branch of node.branches ?? []) {
          if (branch.toNode && !findNode(branch.toNode)) {
            dangling.push(`${node.id} -[${branch.answer}]-> node:${branch.toNode}`)
          }
          if (branch.toStage && !findStage(branch.toStage)) {
            dangling.push(`${node.id} -[${branch.answer}]-> stage:${branch.toStage}`)
          }
        }
      }
    }
    expect(dangling).toEqual([])
  })

  it('gives every branch exactly one destination', () => {
    const bad: string[] = []
    for (const node of allNodes) {
      for (const branch of node.branches ?? []) {
        const targets = [branch.toNode, branch.toStage].filter(Boolean).length
        if (targets !== 1) bad.push(`${node.id} -[${branch.answer}]- has ${targets} targets`)
      }
    }
    expect(bad).toEqual([])
  })

  it('gives every decision node at least two branches, and no other kind any', () => {
    const bad: string[] = []
    for (const node of allNodes) {
      const count = node.branches?.length ?? 0
      if (node.kind === 'decision' && count < 2) bad.push(`${node.id} is a decision with ${count} branches`)
      if (node.kind !== 'decision' && count > 0) bad.push(`${node.id} is a ${node.kind} with branches`)
    }
    expect(bad).toEqual([])
  })

  it('resolves every glossary reference', () => {
    const dangling: string[] = []
    for (const node of allNodes) {
      for (const term of node.glossary ?? []) {
        if (!glossaryEntry(term)) dangling.push(`${node.id} -> ${term}`)
      }
    }
    expect(dangling).toEqual([])
  })

  it('points every app link at a real route', () => {
    // Kept in sync by hand with App.tsx. A link to a route that does not exist
    // renders a blank page, which is worse than no link at all.
    const routes = new Set([
      '/budget', '/accounts', '/transactions', '/liabilities', '/settings',
      '/import', '/reports', '/scheduled', '/payees', '/guide', '/activity',
      '/ai-activity',
    ])
    const bad: string[] = []
    for (const node of allNodes) {
      for (const link of node.appLinks ?? []) {
        if (!routes.has(link.to)) bad.push(`${node.id} -> ${link.to}`)
      }
    }
    expect(bad).toEqual([])
  })

  it('gives every node a title and a body', () => {
    const thin = allNodes
      .filter((n) => !n.title.trim() || n.body.trim().length < 20)
      .map((n) => n.id)
    expect(thin).toEqual([])
  })

  it('uses only step numbers that appear in the legend', () => {
    const legend = new Set(ROADMAP_STEPS.map((s) => s.step))
    const unknown = ROADMAP.filter((s) => !legend.has(s.step)).map((s) => s.id)
    expect(unknown).toEqual([])
  })

  it('leaves no stage unreachable', () => {
    // A stage is reachable if it is the first one, or some branch points into
    // it, or the stage before it can fall through to it. Only explicit jumps
    // are checked here — sequential fallthrough is the default in the UI.
    const reachable = new Set<string>([ROADMAP[0].id])
    ROADMAP.forEach((stage, i) => {
      if (i > 0) reachable.add(stage.id) // sequential fallthrough
    })
    const targeted = allNodes.flatMap((n) => (n.branches ?? []).map((b) => b.toStage))
    for (const t of targeted) if (t) expect(reachable.has(t)).toBe(true)
  })

  it('never sends a branch backwards to an earlier stage', () => {
    // The roadmap is an ordered path. A branch that jumps back would loop the
    // reader; the source chart never does this and neither should we.
    const order = new Map(ROADMAP.map((s, i) => [s.id, i]))
    const backwards: string[] = []
    for (const stage of ROADMAP) {
      for (const node of stage.nodes) {
        for (const branch of node.branches ?? []) {
          if (!branch.toStage) continue
          const from = order.get(stage.id)!
          const to = order.get(branch.toStage)!
          if (to <= from) backwards.push(`${node.id} -> ${branch.toStage}`)
        }
      }
    }
    expect(backwards).toEqual([])
  })

  it('keeps every in-stage branch target inside its own stage', () => {
    // A toNode pointing into a different stage would jump the reader out of
    // context mid-question. Cross-stage movement is what toStage is for.
    const bad: string[] = []
    for (const stage of ROADMAP) {
      const own = new Set(stage.nodes.map((n) => n.id))
      for (const node of stage.nodes) {
        for (const branch of node.branches ?? []) {
          if (branch.toNode && !own.has(branch.toNode)) {
            bad.push(`${node.id} -> ${branch.toNode} (outside ${stage.id})`)
          }
        }
      }
    }
    expect(bad).toEqual([])
  })

  it('marks US-specific content so it can be regionalised later', () => {
    // Guards against a US account type being added without the flag, which is
    // the mistake that would make a future locale filter silently incomplete.
    const usTerms = /\b(401\(?k\)?|403\(?b\)?|IRA|Roth|HSA|529|SEP|SIMPLE)\b/
    const unflagged = allNodes
      .filter((n) => !n.region && usTerms.test(`${n.title} ${n.body}`))
      .map((n) => n.id)
    expect(unflagged).toEqual([])
  })
})
