import { describe, it, expect } from 'vitest'
import { ROADMAP, findStage, type SignalKey, type StageId } from '../../content/roadmap'
import type { CheckupFinding, FindingKind, Signal } from '../../api/guide'
import { roadmapPosition, stageStatus, type PositionInputs } from './roadmapPosition'

function signal(key: SignalKey, over: Partial<Signal> = {}): Signal {
  return {
    key,
    tracked: true,
    source: 'auto',
    met: null,
    value: null,
    detected_value: null,
    external_value: null,
    external_declared: false,
    external_as_of: null,
    target: null,
    starter_target: null,
    starter_met: null,
    reason: '',
    entities: {},
    gaps: [],
    note: null,
    ...over,
  }
}

function finding(kind: FindingKind, concept_key: string, title: string): CheckupFinding {
  return { kind, rank: 1, concept_key, title, detail: '', value: null, target: null, names: [] }
}

function inputs(over: Partial<PositionInputs> = {}): PositionInputs {
  return { progress: {}, leds: new Map(), signals: new Map(), answers: {}, ...over }
}

const signals = (...list: Signal[]) => new Map(list.map((s) => [s.key, s]))
const stage = (id: StageId) => findStage(id)!

/** A budget past Foundation: it exists, and there is an essentials figure. */
const FOUNDED = [
  signal('budget_exists', { met: true }),
  signal('essential_expenses', { met: true }),
]

describe('stageStatus', () => {
  it('the reader’s mark wins over the numbers and the markers', () => {
    const leds = new Map<StageId, CheckupFinding>([
      [
        'starter-emergency-fund',
        finding('ef_not_started', 'emergency_fund', 'No emergency fund yet'),
      ],
    ])
    const unmet = signals(signal('emergency_fund', { met: false, starter_met: false }))
    const done = inputs({ progress: { 'starter-emergency-fund': 'done' }, leds, signals: unmet })
    expect(stageStatus(stage('starter-emergency-fund'), done)).toEqual({
      status: 'done',
      reason: 'you marked this done',
    })
    const skipped = inputs({
      progress: { 'starter-emergency-fund': 'skipped' },
      leds,
      signals: unmet,
    })
    expect(stageStatus(stage('starter-emergency-fund'), skipped).status).toBe('skipped')
  })

  it('a finding lighting the stage opens it, in the finding’s own words', () => {
    const leds = new Map<StageId, CheckupFinding>([
      [
        'high-interest-debt',
        finding('high_interest_debt', 'high_interest_debt', 'Debt at 10% APR or higher'),
      ],
    ])
    expect(stageStatus(stage('high-interest-debt'), inputs({ leds }))).toEqual({
      status: 'open',
      reason: 'Debt at 10% APR or higher',
    })
  })

  it('the starter step reads the starter verdict; the full step reads the full one', () => {
    const between = signals(signal('emergency_fund', { met: false, starter_met: true }))
    expect(stageStatus(stage('starter-emergency-fund'), inputs({ signals: between }))).toEqual({
      status: 'settled',
      reason: 'your budget says so',
    })
    expect(stageStatus(stage('full-emergency-fund'), inputs({ signals: between })).status).toBe(
      'open'
    )
  })

  it('foundation settles once there is a budget and an essentials figure', () => {
    expect(stageStatus(stage('foundation'), inputs({ signals: signals(...FOUNDED) })).status).toBe(
      'settled'
    )
  })

  it('a question the budget cannot answer stays undecided until it is answered', () => {
    expect(stageStatus(stage('employer-match'), inputs()).status).toBe('undecided')
    const unknown = signals(signal('employer_match', { met: null }))
    expect(stageStatus(stage('employer-match'), inputs({ signals: unknown })).status).toBe(
      'undecided'
    )
    expect(
      stageStatus(stage('employer-match'), inputs({ answers: { 'match-question': 'No' } }))
    ).toEqual({
      status: 'settled',
      reason: 'you answered',
    })
  })

  it('an unmet signal opens the stage even with no finding', () => {
    const short = signals(signal('retirement_contributions', { met: false }))
    expect(stageStatus(stage('retirement-fifteen'), inputs({ signals: short })).status).toBe('open')
  })

  it('with personalisation off, only marks and answers speak', () => {
    const off = signals(
      signal('budget_exists', { source: 'off' }),
      signal('essential_expenses', { source: 'off' }),
      signal('emergency_fund', { source: 'off' })
    )
    expect(stageStatus(stage('foundation'), inputs({ signals: off })).status).toBe('undecided')
    expect(
      stageStatus(stage('foundation'), inputs({ signals: off, progress: { foundation: 'done' } }))
        .status
    ).toBe('done')
  })

  it('a dismissed concept gives no verdict either', () => {
    const dismissed = signals(
      ...FOUNDED,
      signal('emergency_fund', { tracked: false, source: 'dismissed' })
    )
    expect(
      stageStatus(stage('starter-emergency-fund'), inputs({ signals: dismissed })).status
    ).toBe('undecided')
  })
})

describe('roadmapPosition', () => {
  it('the cursor is the first stage not behind the reader, in roadmap order', () => {
    const s = signals(...FOUNDED, signal('emergency_fund', { met: false, starter_met: false }))
    const p = roadmapPosition(inputs({ signals: s }))
    expect(p.currentStage).toBe('starter-emergency-fund')
    expect(p.behind).toBe(1)
    expect(p.statuses.size).toBe(ROADMAP.length)
  })

  it('stops on an undecided stage rather than guessing past it', () => {
    const s = signals(...FOUNDED, signal('emergency_fund', { met: true, starter_met: true }))
    const p = roadmapPosition(inputs({ signals: s }))
    expect(p.currentStage).toBe('employer-match')
    expect(p.behind).toBe(2)
  })

  it('follows the marker once the question is answered', () => {
    const s = signals(...FOUNDED, signal('emergency_fund', { met: true, starter_met: true }))
    const leds = new Map<StageId, CheckupFinding>([
      [
        'high-interest-debt',
        finding('high_interest_debt', 'high_interest_debt', 'Debt at 10% APR or higher'),
      ],
    ])
    const p = roadmapPosition(inputs({ signals: s, leds, answers: { 'match-question': 'No' } }))
    expect(p.currentStage).toBe('high-interest-debt')
    expect(p.behind).toBe(3)
  })

  it('everything settled means no current stage', () => {
    const progress = Object.fromEntries(ROADMAP.map((s) => [s.id, 'done' as const]))
    const p = roadmapPosition(inputs({ progress }))
    expect(p.currentStage).toBeNull()
    expect(p.behind).toBe(ROADMAP.length)
  })
})
