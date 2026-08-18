/**
 * Target funding semantics — a deliberate mirror of the backend's
 * TargetService.calculate_status (backend/src/igab/services/target_service.py).
 *
 * Every surface that says "funded"/"underfunded" (the row pill, the quick
 * filters, the view-bar counts) MUST go through this module. This code exists
 * because three components each hand-rolled `assigned >= target_amount`,
 * which is only right for monthly/weekly funding: a savings-balance target
 * measures AVAILABLE (the balance you are building), so a category whose
 * balance already met the goal showed a full progress bar next to an
 * "Underfunded" pill. If you change the rules here, change the backend to
 * match — Fill Underfunded (assign_service) uses the same math and the pill
 * must predict what it will do.
 */
import type { CategoryTarget } from '../types'

export type TargetStatus = 'funded' | 'underfunded' | 'overfunded'

/** Whole months from `start` to `end`, minimum 1 — mirrors _months_between. */
export function monthsBetween(start: Date, end: Date): number {
  return Math.max(
    1,
    (end.getFullYear() - start.getFullYear()) * 12 + (end.getMonth() - start.getMonth())
  )
}

/**
 * The amount that must be ASSIGNED this month for the target to count as
 * funded. Can be negative (a dated goal already exceeded); callers that
 * display it should clamp at 0.
 *
 *  - monthly/weekly funding: the full amount, every period, rollover ignored
 *  - savings balance: the remaining shortfall (available counts)
 *  - needed for spending with a date: the shortfall spread over the months
 *    left — the monthly pace
 */
export function targetNeededThisMonth(
  target: Pick<CategoryTarget, 'target_type' | 'target_amount' | 'target_date'>,
  available: number,
  now: Date = new Date()
): number {
  const amount = Number(target.target_amount)
  switch (target.target_type) {
    case 'savings_balance':
      return Math.max(0, amount - available)
    case 'needed_for_spending':
      if (target.target_date) {
        const months = monthsBetween(now, new Date(target.target_date + 'T00:00:00'))
        return (amount - available) / months
      }
      return amount
    default:
      // monthly_funding, weekly_funding, and any future type until it gets
      // its own rule — same fallback the backend uses.
      return amount
  }
}

export function targetStatus(
  target: Pick<CategoryTarget, 'target_type' | 'target_amount' | 'target_date'>,
  assigned: number,
  available: number,
  now: Date = new Date()
): TargetStatus {
  const needed = targetNeededThisMonth(target, available, now)
  if (assigned >= needed) {
    // Same 5% grace as the backend before calling it overfunded.
    return assigned > needed * 1.05 ? 'overfunded' : 'funded'
  }
  return 'underfunded'
}

/**
 * Progress toward the target's own measure, 0..1.
 *
 * Balance-shaped targets (savings balance, dated needed-for-spending) fill by
 * AVAILABLE — the bar answers "how much of the goal balance exists". Funding
 * targets fill by ASSIGNED — "how much of this month's duty is done". Using
 * the same measure as targetStatus is what keeps the bar and the pill from
 * ever disagreeing.
 */
export function targetProgress(
  target: Pick<CategoryTarget, 'target_type' | 'target_amount' | 'target_date'>,
  assigned: number,
  available: number
): number | null {
  const amount = Number(target.target_amount)
  if (amount <= 0) return null
  const numerator = targetMeasuresBalance(target) ? available : assigned
  return Math.min(Math.max(numerator / amount, 0), 1)
}

/** Whether the target is a balance goal (progress/remaining read AVAILABLE). */
export function targetMeasuresBalance(
  target: Pick<CategoryTarget, 'target_type' | 'target_date'>
): boolean {
  return (
    target.target_type === 'savings_balance' ||
    (target.target_type === 'needed_for_spending' && !!target.target_date)
  )
}
