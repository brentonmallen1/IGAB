/**
 * How a served plan reads beside its parts — the one wording Budget vs Actual's
 * table and Plan vs Reality's cell title share.
 *
 * The plan itself is the server's (`plan = max(assigned + moved_in -
 * moved_out, 0)`, backend `domain/plan.py`); this only names the terms that
 * moved it, and never adds them. Each report spelled its own: Budget vs Actual
 * said "(M moved in)" and Plan vs Reality "(assigned A + moved in M)", and
 * neither could say money had moved out.
 */
export interface PlanParts {
  assigned: number
  moved_in: number
  moved_out: number
  plan: number
}

export function planLabel(parts: PlanParts, formatMoney: (n: number) => string): string {
  const plan = formatMoney(parts.plan)
  if (parts.moved_in === 0 && parts.moved_out === 0) return plan
  const terms = [`assigned ${formatMoney(parts.assigned)}`]
  if (parts.moved_in !== 0) terms.push(`+ moved in ${formatMoney(parts.moved_in)}`)
  if (parts.moved_out !== 0) terms.push(`− moved out ${formatMoney(parts.moved_out)}`)
  return `${plan} (${terms.join(' ')})`
}
