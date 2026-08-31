import { describe, it, expect } from 'vitest'
import { ROADMAP } from '../../content/roadmap'
import type { CheckupFinding, FindingKind } from '../../api/guide'
import {
  FINDING_STAGES,
  FINDINGS_SHOWN,
  ledStages,
  splitFindings,
  stagesForFinding,
} from './checkupLeds'

function finding(kind: FindingKind, concept_key: string | null = null, rank = 1): CheckupFinding {
  return { kind, rank, concept_key, title: kind, detail: '', value: null, target: null, names: [] }
}

const STAGE_IDS = new Set(ROADMAP.map((s) => s.id))

describe('checkupLeds', () => {
  it('maps every finding kind to a real stage', () => {
    for (const stage of Object.values(FINDING_STAGES)) expect(STAGE_IDS.has(stage)).toBe(true)
    const stale = stagesForFinding(finding('stale_external', 'emergency_fund'))
    expect(stale.length).toBeGreaterThan(0)
    for (const stage of stale) expect(STAGE_IDS.has(stage)).toBe(true)
  })

  it('a stale emergency-fund figure lights both emergency-fund stages', () => {
    expect(stagesForFinding(finding('stale_external', 'emergency_fund')).sort()).toEqual([
      'full-emergency-fund',
      'starter-emergency-fund',
    ])
  })

  it('a stale figure for a concept no stage reads lights nothing', () => {
    expect(stagesForFinding(finding('stale_external', 'not-a-concept'))).toEqual([])
    expect(stagesForFinding(finding('stale_external', null))).toEqual([])
  })

  it('a marked stage is never lit — the user’s mark wins', () => {
    const lit = ledStages([finding('high_interest_debt'), finding('chronic_overspend')], {
      'high-interest-debt': 'done',
    })
    expect(lit.has('high-interest-debt')).toBe(false)
    expect(lit.has('foundation')).toBe(true)
    const skipped = ledStages([finding('chronic_overspend')], { foundation: 'skipped' })
    expect(skipped.size).toBe(0)
  })

  it('keeps the most severe finding for a stage that two findings name', () => {
    const lit = ledStages(
      [finding('high_interest_debt', null, 1), finding('unknown_rates', null, 8)],
      {}
    )
    expect(lit.get('high-interest-debt')?.kind).toBe('high_interest_debt')
  })

  it('shows five and counts the rest', () => {
    const seven = Array.from({ length: 7 }, (_, i) => i)
    expect(splitFindings(seven)).toEqual({ shown: [0, 1, 2, 3, 4], more: 2 })
    expect(FINDINGS_SHOWN).toBe(5)
  })

  it('a short list has no remainder', () => {
    expect(splitFindings([1, 2, 3, 4])).toEqual({ shown: [1, 2, 3, 4], more: 0 })
    expect(splitFindings([])).toEqual({ shown: [], more: 0 })
  })
})
