import { describe, expect, it } from 'vitest'
import { CHART_COLORS, chartColor } from './chartColors'

describe('chartColor', () => {
  it('assigns the themed slots in order', () => {
    CHART_COLORS.forEach((c, i) => expect(chartColor(i)).toBe(c))
  })

  it('repeats the palette rather than greying the tail', () => {
    // It used to return one flat "Other" grey past the eighth series, which
    // made Cost of Living's ninth group indistinguishable from its twelfth —
    // and, while the chart also capped its bars at eight, invisible entirely.
    expect(chartColor(CHART_COLORS.length)).toBe(CHART_COLORS[0])
    expect(chartColor(CHART_COLORS.length + 3)).toBe(CHART_COLORS[3])
  })

  it('never returns undefined, however many series a budget has', () => {
    for (let i = 0; i < 100; i++) expect(chartColor(i)).toMatch(/^var\(--chart-\d\)$/)
  })
})
