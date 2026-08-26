import { ROADMAP, type SignalKey, type StageId } from '../../content/roadmap'
import type { CheckupFinding, FindingKind } from '../../api/guide'

/**
 * Which roadmap step a finding belongs to, and which steps get the quiet
 * amber marker.
 *
 * The server knows concepts and findings; it never knows stages — those are
 * roadmap content, which lives on this side. So the one place a finding kind
 * is tied to a step is this table, and the marker is derived from it rather
 * than served. Pure, so every row is a one-line test.
 */

/** Kinds that name their step outright. `stale_external` follows its concept
 *  instead: a stale emergency-fund figure marks both emergency-fund steps. */
export const FINDING_STAGES: Record<Exclude<FindingKind, 'stale_external'>, StageId> = {
  high_interest_debt: 'high-interest-debt',
  ef_below_starter: 'starter-emergency-fund',
  chronic_overspend: 'foundation',
  ef_below_full: 'full-emergency-fund',
  moderate_debt: 'moderate-interest-debt',
  retirement_below_target: 'retirement-fifteen',
  unknown_rates: 'high-interest-debt',
}

/** Every stage with a node that reads this concept. Derived from the content
 *  so a node moving between stages cannot strand its marker. */
export function stagesForSignal(key: SignalKey): StageId[] {
  return ROADMAP.filter((s) => s.nodes.some((n) => n.signal === key)).map((s) => s.id)
}

export function stagesForFinding(finding: CheckupFinding): StageId[] {
  if (finding.kind === 'stale_external') {
    return finding.concept_key ? stagesForSignal(finding.concept_key as SignalKey) : []
  }
  return [FINDING_STAGES[finding.kind]]
}

/**
 * Stage → the finding that lights it (the most severe, since findings arrive
 * ranked). A stage the user marked done or skipped is never lit: their mark
 * wins over the numbers, quietly.
 */
export function ledStages(
  findings: CheckupFinding[],
  progress: Record<string, 'done' | 'skipped'>
): Map<StageId, CheckupFinding> {
  const lit = new Map<StageId, CheckupFinding>()
  for (const finding of findings) {
    for (const stage of stagesForFinding(finding)) {
      if (progress[stage]) continue
      if (!lit.has(stage)) lit.set(stage, finding)
    }
  }
  return lit
}

/** How many findings the health report shows before "and N more". An honest
 *  tool that finds twelve problems still shows the five that matter — a wall
 *  of amber is how people learn to stop pressing the button. */
export const FINDINGS_SHOWN = 5

export function splitFindings<T>(findings: T[]): { shown: T[]; more: number } {
  return {
    shown: findings.slice(0, FINDINGS_SHOWN),
    more: Math.max(0, findings.length - FINDINGS_SHOWN),
  }
}
