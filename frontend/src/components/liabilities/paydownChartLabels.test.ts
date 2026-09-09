import { describe, expect, it } from 'vitest'
import { referenceLabel, referenceLabelAnchor } from './paydownChartLabels'

/** A year of months, so a position is easy to reason about by index. */
const MONTHS = [
  '2026-01',
  '2026-02',
  '2026-03',
  '2026-04',
  '2026-05',
  '2026-06',
  '2026-07',
  '2026-08',
  '2026-09',
  '2026-10',
  '2026-11',
  '2026-12',
]

describe('referenceLabelAnchor', () => {
  it('anchors the last month to the end, which is what clipped "Live payoff"', () => {
    // The bug: the payoff marker sits on the final point of the axis, and a
    // centred label there loses its right half to the plot edge — the paydown
    // chart drew "Live payo".
    expect(referenceLabelAnchor('2026-12', MONTHS)).toBe('end')
  })

  it('anchors the first month to the start', () => {
    expect(referenceLabelAnchor('2026-01', MONTHS)).toBe('start')
  })

  it('leaves a marker in the middle centred on its line', () => {
    expect(referenceLabelAnchor('2026-06', MONTHS)).toBe('middle')
    expect(referenceLabelAnchor('2026-07', MONTHS)).toBe('middle')
  })

  it('treats a month just inside an edge as an edge', () => {
    // 12 months: the band is the outer 5%, so index 0 and index 11 only —
    // the second month sits a tenth of the way across and stays centred.
    expect(referenceLabelAnchor('2026-02', MONTHS)).toBe('middle')
    // On a short axis the band reaches further, because a label is a larger
    // share of a short plot.
    expect(referenceLabelAnchor('b', ['a', 'b', 'c'])).toBe('middle')
    expect(referenceLabelAnchor('c', ['a', 'b', 'c'])).toBe('end')
  })

  it('centres a month the axis does not draw, and a single-point axis', () => {
    expect(referenceLabelAnchor('2027-04', MONTHS)).toBe('middle')
    expect(referenceLabelAnchor('a', ['a'])).toBe('middle')
    expect(referenceLabelAnchor('a', [])).toBe('middle')
  })
})

describe('referenceLabel', () => {
  it('gives every marker the same shape, clamp included', () => {
    expect(referenceLabel('Live payoff', '2026-12', MONTHS, 'green')).toEqual({
      value: 'Live payoff',
      fontSize: 11,
      fill: 'green',
      position: 'top',
      textAnchor: 'end',
    })
  })

  it('carries the caller’s colour through unchanged', () => {
    const label = referenceLabel('Today', '2026-06', MONTHS, 'var(--text-muted)')
    expect(label.fill).toBe('var(--text-muted)')
    expect(label.textAnchor).toBe('middle')
  })
})
