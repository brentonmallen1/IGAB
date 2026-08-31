import { describe, it, expect } from 'vitest'
import { stagePath, stageAnswered } from './journeyPath'
import { ROADMAP, findStage, type RoadmapStage } from '../../content/roadmap'

const employerMatch = findStage('employer-match') as RoadmapStage
const highInterest = findStage('high-interest-debt') as RoadmapStage
const foundation = findStage('foundation') as RoadmapStage

describe('stagePath', () => {
  it('shows every node of a stage with no decisions', () => {
    const path = stagePath(foundation, {})
    expect(path.visible).toEqual(foundation.nodes.map((n) => n.id))
    expect(path.pending).toEqual([])
    expect(path.skipped).toEqual([])
    expect(path.exitTo).toBeNull()
  })

  it('holds later nodes as pending while a decision is unanswered', () => {
    const path = stagePath(employerMatch, {})
    expect(path.visible).toEqual(['match-question'])
    expect(path.pending).toEqual(['contribute-to-match'])
    expect(path.skipped).toEqual([])
  })

  it('follows a yes answer to its target node', () => {
    const path = stagePath(employerMatch, { 'match-question': 'Yes' })
    expect(path.visible).toEqual(['match-question', 'contribute-to-match'])
    expect(path.pending).toEqual([])
    expect(path.skipped).toEqual([])
    expect(path.exitTo).toBeNull()
  })

  it('skips the rest of the stage when an answer exits to another stage', () => {
    const path = stagePath(employerMatch, { 'match-question': 'No' })
    expect(path.visible).toEqual(['match-question'])
    expect(path.skipped).toEqual(['contribute-to-match'])
    expect(path.skipReason['contribute-to-match']).toBe('No')
    expect(path.exitTo).toBe('high-interest-debt')
  })

  it('records the exit target so the reader can be told where they are going', () => {
    const path = stagePath(highInterest, { 'high-interest-question': 'No' })
    expect(path.exitTo).toBe('full-emergency-fund')
    expect(path.skipped).toContain('choose-payoff-method')
  })

  it('treats a stale answer that matches no branch as unanswered', () => {
    // Content edited under a persisted answer — must not crash or mis-route.
    const path = stagePath(employerMatch, { 'match-question': 'Maybe someday' })
    expect(path.visible).toEqual(['match-question'])
    expect(path.pending).toEqual(['contribute-to-match'])
    expect(path.exitTo).toBeNull()
  })

  it('never lists a node in more than one state', () => {
    for (const stage of ROADMAP) {
      for (const answers of [{}, firstAnswers(stage), secondAnswers(stage)]) {
        const p = stagePath(stage, answers)
        const all = [...p.visible, ...p.pending, ...p.skipped]
        expect(new Set(all).size).toBe(all.length)
      }
    }
  })

  it('accounts for every node in the stage, whatever the answers', () => {
    for (const stage of ROADMAP) {
      for (const answers of [{}, firstAnswers(stage), secondAnswers(stage)]) {
        const p = stagePath(stage, answers)
        const seen = new Set([...p.visible, ...p.pending, ...p.skipped])
        // Nodes after an exit are skipped; nodes after an unanswered decision
        // are pending. Either way nothing may silently vanish.
        expect(seen.size).toBe(stage.nodes.length)
      }
    }
  })

  it('always shows at least the first node', () => {
    for (const stage of ROADMAP) {
      expect(stagePath(stage, {}).visible[0]).toBe(stage.nodes[0].id)
    }
  })
})

describe('stageAnswered', () => {
  it('is false while a reachable decision is unanswered', () => {
    expect(stageAnswered(employerMatch, {})).toBe(false)
  })

  it('is true when every reachable decision has an answer', () => {
    expect(stageAnswered(employerMatch, { 'match-question': 'Yes' })).toBe(true)
  })

  it('ignores decisions the chosen path never reaches', () => {
    // Answering "No" exits the stage, so nothing further needs answering.
    expect(stageAnswered(employerMatch, { 'match-question': 'No' })).toBe(true)
  })

  it('is true for a stage with no decisions at all', () => {
    expect(stageAnswered(foundation, {})).toBe(true)
  })
})

/** Answer every decision with its first branch. */
function firstAnswers(stage: RoadmapStage): Record<string, string> {
  const out: Record<string, string> = {}
  for (const n of stage.nodes) if (n.branches?.length) out[n.id] = n.branches[0].answer
  return out
}

/** Answer every decision with its last branch. */
function secondAnswers(stage: RoadmapStage): Record<string, string> {
  const out: Record<string, string> = {}
  for (const n of stage.nodes)
    if (n.branches?.length) out[n.id] = n.branches[n.branches.length - 1].answer
  return out
}
