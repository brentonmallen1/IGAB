/** Pure presentation for Cumulative Variance: every figure is served. */
import type { VariancePoint } from '../../../types'
import { COLOR_NEGATIVE, COLOR_POSITIVE } from './chartColors'

/** A month's bar colour, by its state: red over plan, green under. The chart
 *  drew a Spent bar red in EVERY month, so an on-plan year read as a wall of
 *  overspending beside a line saying the opposite. */
export function varianceBarColor(monthlyVariance: number): string {
  return monthlyVariance < 0 ? COLOR_NEGATIVE : COLOR_POSITIVE
}

/** What the tooltip lists for one month, in reading order: the plan, what was
 *  spent, the month's gap (the bar) and the running total (the line). The
 *  plan and spending are not drawn — on one axis beside a year's running
 *  total they were slivers, and on a second axis the two zeros sat at
 *  different heights, so the line crossed "zero" where it was not. */
export function varianceTooltipRows(
  p: VariancePoint
): { name: string; value: number; color?: string }[] {
  return [
    { name: 'Planned', value: p.planned },
    { name: 'Spent', value: p.actual_spent },
    {
      name: p.monthly_variance < 0 ? 'Over plan' : 'Under plan',
      value: Math.abs(p.monthly_variance),
      color: varianceBarColor(p.monthly_variance),
    },
    { name: 'Running total', value: p.cumulative_variance },
  ]
}
