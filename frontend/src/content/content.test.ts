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

  it('matches the source chart box for box, in order', () => {
    // Locked against the r/personalfinance flowchart. If a node is added,
    // removed or reordered, update the source map in roadmap.ts first and
    // make sure the change is actually faithful — then update this list.
    expect(allNodes.map((n) => n.id)).toEqual([
      // Step 0 — budget and essentials
      'create-budget',
      'housing',
      'groceries',
      'essential-items',
      'income-earning-expenses',
      'health-care',
      'minimum-payments',
      // Step 1 — starter emergency fund
      'starter-ef',
      'nonessential-bills',
      // Step 2 — employer match
      'match-question',
      'contribute-to-match',
      // Step 3 — high interest debt
      'high-interest-question',
      'choose-payoff-method',
      // Step 1 again — full emergency fund
      'full-ef',
      // Step 3 again — moderate interest debt
      'moderate-interest-question',
      'pay-moderate-debt',
      // Step 4 — IRA and near-term needs
      'roth-vs-traditional',
      'large-purchase-question',
      'save-for-purchase',
      // Step 5 — 15% for retirement
      'fifteen-percent-question',
      'employer-plan-question',
      'increase-contributions',
      'self-employed-options',
      // Step 6 — other goals
      'hsa-question',
      'max-hsa',
      'college-question',
      'college-savings',
      'your-call',
      'retire-early',
      'immediate-goals',
    ])
  })

  it('keeps each stage on the step number the source colours it', () => {
    // Steps 1 and 3 each appear twice — the chart genuinely revisits the
    // emergency fund and debt. That repetition is the content, not a bug.
    expect(ROADMAP.map((s) => [s.id, s.step])).toEqual([
      ['foundation', 0],
      ['starter-emergency-fund', 1],
      ['employer-match', 2],
      ['high-interest-debt', 3],
      ['full-emergency-fund', 1],
      ['moderate-interest-debt', 3],
      ['retirement-and-near-term', 4],
      ['retirement-fifteen', 5],
      ['other-goals', 6],
    ])
  })

  it('routes every decision exactly as the source chart does', () => {
    const route = (nodeId: string, answer: string) => {
      const b = findNode(nodeId)!.node.branches!.find((x) => x.answer === answer)!
      return b.toNode ?? b.toStage
    }
    // Employer match: yes -> contribute; no -> straight to high interest debt.
    expect(route('match-question', 'Yes')).toBe('contribute-to-match')
    expect(route('match-question', 'No')).toBe('high-interest-debt')
    // High interest: yes -> payoff method; no -> grow the emergency fund.
    expect(route('high-interest-question', 'Yes')).toBe('choose-payoff-method')
    expect(route('high-interest-question', 'No')).toBe('full-emergency-fund')
    // Moderate interest: no -> the IRA step.
    expect(route('moderate-interest-question', 'Yes')).toBe('pay-moderate-debt')
    expect(route('moderate-interest-question', 'No')).toBe('retirement-and-near-term')
    // Large purchase: yes -> save it in cash; no -> the 15% question.
    expect(route('large-purchase-question', 'Yes')).toBe('save-for-purchase')
    expect(route('large-purchase-question', 'No')).toBe('retirement-fifteen')
    // 15%: yes -> skip ahead to other goals; no -> check the employer plan.
    expect(route('fifteen-percent-question', 'Yes')).toBe('other-goals')
    expect(route('fifteen-percent-question', 'No')).toBe('employer-plan-question')
    expect(route('employer-plan-question', 'Yes')).toBe('increase-contributions')
    expect(route('employer-plan-question', 'No')).toBe('self-employed-options')
    // Step 6 chain.
    expect(route('hsa-question', 'Yes')).toBe('max-hsa')
    expect(route('hsa-question', 'No')).toBe('college-question')
    expect(route('college-question', 'Yes')).toBe('college-savings')
    expect(route('college-question', 'No')).toBe('your-call')
  })

  it('states the source thresholds without inventing precision', () => {
    const text = allNodes.map((n) => `${n.title} ${n.body} ${n.detail ?? ''}`).join(' ')
    expect(text).toContain('10% or higher')       // high interest
    expect(text).toContain('4–5%')                 // moderate interest
    expect(text).toContain('15%')                  // retirement target
    expect(text).toContain('three to six months')  // full emergency fund
    expect(text).toContain('$1,000')               // starter emergency fund
  })

  it('never states a figure that changes yearly', () => {
    // Contribution caps and tax brackets go stale and quietly become wrong.
    // "the yearly limit" ages well; "$7,000" does not.
    const offenders: string[] = []
    for (const node of allNodes) {
      const text = `${node.title} ${node.body} ${node.detail ?? ''}`
      // Any dollar figure other than the source's fixed $1,000 starter fund.
      const amounts = text.match(/\$[\d,]*\d/g) ?? []
      for (const a of amounts) if (a !== '$1,000') offenders.push(`${node.id}: ${a}`)
    }
    expect(offenders).toEqual([])
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
