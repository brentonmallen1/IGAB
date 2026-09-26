/** Colours by state, not by series: red only where the figure is bad news. */
import { describe, expect, it } from 'vitest'
import { historySpentColor } from './categoryHistoryView'
import { CHART_COLORS, COLOR_NEGATIVE, COLOR_POSITIVE } from './chartColors'
import { varianceBarColor, varianceTooltipRows } from './varianceView'

describe('Cumulative Variance', () => {
  it('colours a month red only when it went over plan', () => {
    // Spent was red in every month, so an on-plan year drew as a wall of
    // overspending beside a line saying the opposite.
    expect(varianceBarColor(-50)).toBe(COLOR_NEGATIVE)
    expect(varianceBarColor(0)).toBe(COLOR_POSITIVE)
    expect(varianceBarColor(120)).toBe(COLOR_POSITIVE)
  })

  it('lists plan, spent, the month and the running total in its tooltip', () => {
    const rows = varianceTooltipRows({
      month: '2026-08-01',
      budget_assigned: 900,
      moved_in: 100,
      planned: 1000,
      actual_spent: 1150,
      monthly_variance: -150,
      cumulative_variance: -400,
    })
    expect(rows.map((r) => [r.name, r.value])).toEqual([
      ['Planned', 1000],
      ['Spent', 1150],
      ['Over plan', 150],
      ['Running total', -400],
    ])
  })
})

describe('Category History historySpentColor', () => {
  it('is red only in a month the envelope ended overspent', () => {
    // Assigned green and Spent red in every month drew a category that never
    // overspent as twelve red bars.
    expect(historySpentColor(-10)).toBe(COLOR_NEGATIVE)
    expect(historySpentColor(0)).toBe(CHART_COLORS[0])
    expect(historySpentColor(250)).toBe(CHART_COLORS[0])
  })

  it('is neutral for an income category, which holds no money', () => {
    expect(historySpentColor(null)).toBe(CHART_COLORS[0])
  })
})
