/**
 * How the served General Savings month reads. Composition of served facts
 * only: every amount below arrived in the response.
 */
import type { MoneyMonthResponse } from '../../../api/moneyRules'

/** What the envelope holds at the month's end: the served envelope term of
 * every move, added up. The same either way — the mode changes what counts as
 * saved, never where the money is. */
export function envelopeLeft(month: MoneyMonthResponse): number {
  const cents = month.rows
    .flatMap((row) => row.explanation.budget_terms)
    .filter((t) => t.term === 'envelope')
    .reduce((sum, t) => sum + Math.round(t.delta * 100), 0)
  return cents / 100
}
