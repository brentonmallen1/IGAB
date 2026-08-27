/**
 * What the pattern chips are built from — shared by the merge modal and the
 * Payees page editor, so both offer the same list in the same order.
 */

export interface PatternCandidate {
  pattern: string
  /** Where it came from — the model, or the shared structure of the names. */
  source: 'ai' | 'structural'
}

/** What to say when nothing the model proposed matched even one name. */
export const NO_PATTERN_MESSAGE = "The AI's patterns matched none of these names."

/** The chips to offer: the model's candidates in served order (most specific
 *  first), then the structural suggestion unless the model already gave it. */
export function patternCandidates(ai: string[], structural: string | null): PatternCandidate[] {
  const list: PatternCandidate[] = ai.map((pattern) => ({ pattern, source: 'ai' }))
  if (structural && !ai.includes(structural)) list.push({ pattern: structural, source: 'structural' })
  return list
}
