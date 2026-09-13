/**
 * Presentation of the server's money explanations (`api/moneyRules.ts`).
 *
 * Composition only: which served shape an account type lands on, and how a
 * served budget term reads as a sentence. No class, family or term is decided
 * here — the server answers those from the rules the reports run.
 */
import type { BudgetTerm, Classification, MoneyShape } from '../api/moneyRules'

export interface ShapeFacts {
  classification: Classification
  on_budget: boolean
  counts_as_savings: boolean
}

/** The served shape these three facts describe. A shape whose
 * `counts_as_savings` is null matches either value — the flag changes
 * nothing there, which the server states by serving null. */
export function shapeFor(shapes: readonly MoneyShape[], facts: ShapeFacts): MoneyShape | undefined {
  return shapes.find(
    (s) =>
      s.classification === facts.classification &&
      s.on_budget === facts.on_budget &&
      (s.counts_as_savings === null || s.counts_as_savings === facts.counts_as_savings)
  )
}

export const BUDGET_TERM_LABEL: Record<BudgetTerm, string> = {
  ready_to_assign: 'Ready to Assign',
  envelope: 'The category',
  card_set_aside: "The card's Ready to pay",
  card_uncovered: "The card's Uncovered",
}

/** "Ready to Assign goes down by $1,000." */
export function budgetTermSentence(
  term: BudgetTerm,
  delta: number,
  formatMoney: (n: number) => string
): string {
  const way = delta > 0 ? 'goes up' : 'goes down'
  return `${BUDGET_TERM_LABEL[term]} ${way} by ${formatMoney(Math.abs(delta))}`
}

/** One line for a move's budget effect, or the served "nothing moves". */
export function budgetEffectLines(
  terms: readonly { term: BudgetTerm; delta: number }[],
  formatMoney: (n: number) => string
): string[] {
  if (terms.length === 0) return ['No budget figure moves']
  return terms.map((t) => budgetTermSentence(t.term, t.delta, formatMoney))
}
