/** Colours by state, not by series: red only where the figure is bad news. */
import { describe, expect, it } from 'vitest'
import { historySpentColor } from './categoryHistoryView'
import { CHART_COLORS, COLOR_NEGATIVE } from './chartColors'

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
